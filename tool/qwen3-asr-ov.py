#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Qwen3-ASR MiniTool CLI (OpenVINO CPU 版本)
使用 QwenASRMiniTool 的 OpenVINO INT8 量化模型，CPU 推理

用法:
    python qwen3-asr-ov.py -i audio.mp3 -o output.srt
    python qwen3-asr-ov.py -i audio.mp3 -o output.srt -l Japanese
    python qwen3-asr-ov.py -i audio.mp3 -o output.srt --diarize --speakers 2
"""

import argparse
import os
import sys
import time
from pathlib import Path

# 設定 stdout 編碼為 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 預設路徑
DEFAULT_MODEL_DIR = Path(r"D:\Python\QwenASR\ov_models")
DEFAULT_OUTPUT_DIR = Path(r"D:\Python\Subtitle_AI_translator\temp\asr_output")

# 支援的語言
LANGUAGES = [
    "Chinese", "English", "Japanese", "Korean", "French", "German",
    "Spanish", "Portuguese", "Russian", "Arabic", "Thai", "Vietnamese",
    "Indonesian", "Malay", "Cantonese"
]

# SAMPLE_RATE = 16000
SAMPLE_RATE = 16000


def find_qwen_asr_ov():
    """找到 QwenASR 的 OpenVINO 模型目錄"""
    candidates = [
        Path(r"D:\Python\QwenASR\ov_models"),
        Path(r"D:\Python\QwenASR\source\ov_models"),
    ]
    for p in candidates:
        if p.exists() and (p / "qwen3_asr_int8").exists():
            return p
    return None


def get_audio_files(paths):
    """取得音頻檔案列表"""
    audio_exts = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
    files = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            if p.suffix.lower() in audio_exts:
                files.append(p)
        elif p.is_dir():
            for f in p.rglob('*'):
                if f.suffix.lower() in audio_exts:
                    files.append(f)
    return files


def detect_speech_groups(audio, vad_sess, max_group_sec=20):
    """VAD 靜音偵測分段"""
    import numpy as np

    VAD_CHUNK = 512
    VAD_THRESHOLD = 0.5

    h = np.zeros((2, 1, 64), dtype=np.float32)
    c = np.zeros((2, 1, 64), dtype=np.float32)
    sr = np.array(SAMPLE_RATE, dtype=np.int64)
    n = len(audio) // VAD_CHUNK
    probs = []
    for i in range(n):
        chunk = audio[i*VAD_CHUNK:(i+1)*VAD_CHUNK].astype(np.float32)[np.newaxis, :]
        out, h, c = vad_sess.run(None, {"input": chunk, "h": h, "c": c, "sr": sr})
        probs.append(float(out[0, 0]))
    if not probs:
        return [(0.0, len(audio) / SAMPLE_RATE, audio)]

    MIN_CH = 16
    PAD = 5
    MERGE = 16
    raw = []
    in_sp = False
    s0 = 0
    for i, p in enumerate(probs):
        if p >= VAD_THRESHOLD and not in_sp:
            s0 = i
            in_sp = True
        elif p < VAD_THRESHOLD and in_sp:
            if i - s0 >= MIN_CH:
                raw.append((max(0, s0-PAD), min(n, i+PAD)))
            in_sp = False
    if in_sp and n - s0 >= MIN_CH:
        raw.append((max(0, s0-PAD), n))
    if not raw:
        return []

    merged = [list(raw[0])]
    for s, e in raw[1:]:
        if s - merged[-1][1] <= MERGE:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    mx_samp = max_group_sec * SAMPLE_RATE
    groups = []
    gs = merged[0][0] * VAD_CHUNK
    ge = merged[0][1] * VAD_CHUNK
    for seg in merged[1:]:
        s = seg[0] * VAD_CHUNK
        e = seg[1] * VAD_CHUNK
        if e - gs > mx_samp:
            groups.append((gs, ge))
            gs = s
        ge = e
    groups.append((gs, ge))

    result = []
    for gs, ge in groups:
        ns = max(1, int((ge - gs) // SAMPLE_RATE))
        ch = audio[gs: gs + ns * SAMPLE_RATE].astype(np.float32)
        if len(ch) < SAMPLE_RATE:
            continue
        result.append((gs / SAMPLE_RATE, gs / SAMPLE_RATE + ns, ch))
    return result


def split_to_lines(text):
    """將文字分段為行"""
    import re
    MAX_CHARS = 20
    GAP_SEC = 0.08
    MIN_SUB_SEC = 0.6

    text = text.strip()
    if not text:
        return []

    parts = re.split(r"[。！？，、；：…—,.!?;:]+", text)
    lines = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        while len(p) > MAX_CHARS:
            lines.append(p[:MAX_CHARS])
            p = p[MAX_CHARS:]
        lines.append(p)
    return [l for l in lines if l.strip()]


def srt_ts(s):
    """秒數轉 SRT 時間格式"""
    ms = int(round(s * 1000))
    hh = ms // 3_600_000
    ms %= 3_600_000
    mm = ms // 60_000
    ms %= 60_000
    ss = ms // 1_000
    ms %= 1_000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def assign_ts(lines, g0, g1):
    """分配時間軸"""
    if not lines:
        return []
    total = sum(len(l) for l in lines)
    if total == 0:
        return []
    dur = g1 - g0
    res = []
    cur = g0
    GAP_SEC = 0.08
    MIN_SUB_SEC = 0.6
    for i, line in enumerate(lines):
        end = cur + max(MIN_SUB_SEC, dur * len(line) / total)
        if i == len(lines) - 1:
            end = max(end, g1)
        res.append((cur, end, line))
        cur = end + GAP_SEC
    return res


class QwenASROpenVINO:
    """Qwen3-ASR OpenVINO CPU 推理引擎"""

    max_chunk_secs = 30

    def __init__(self, model_dir=None, cpu_threads=0):
        self.model_dir = Path(model_dir) if model_dir else None
        self.cpu_threads = cpu_threads
        self.ready = False

        # 延遲載入
        self.vad_sess = None
        self.audio_enc = None
        self.embedder = None
        self.dec_req = None
        self.processor = None
        self.pad_id = None
        self.cc = None

    def load(self, device="CPU"):
        """載入模型"""
        import openvino as ov
        import onnxruntime as ort
        import opencc

        # 嘗試自動找到模型目錄
        if self.model_dir is None:
            self.model_dir = find_qwen_asr_ov()

        if self.model_dir is None or not (self.model_dir / "qwen3_asr_int8").exists():
            raise FileNotFoundError(
                f"找不到 Qwen3-ASR OpenVINO 模型！\n"
                f"請確認模型路徑：{self.model_dir}\n"
                f"或從 https://github.com/dseditor/QwenASRMiniTool 下載"
            )

        ov_dir = self.model_dir / "qwen3_asr_int8"

        print(f"[INFO] 模型目錄: {self.model_dir}")
        print(f"[INFO] 裝置: {device}")

        # CPU 設定
        cpu_cfg = {}
        if device == "CPU":
            cpu_cfg["PERFORMANCE_HINT"] = "LATENCY"
            cpu_cfg["ENABLE_HYPER_THREADING"] = "YES"
            if self.cpu_threads > 0:
                cpu_cfg["INFERENCE_NUM_THREADS"] = str(self.cpu_threads)

        # 載入 VAD
        print("[INFO] 載入 VAD 模型...")
        vad_path = self.model_dir / "silero_vad_v4.onnx"
        self.vad_sess = ort.InferenceSession(
            str(vad_path), providers=["CPUExecutionProvider"]
        )

        # 載入 ASR 模型
        print("[INFO] 載入 ASR 模型 (OpenVINO)...")
        core = ov.Core()
        self.audio_enc = core.compile_model(
            str(ov_dir / "audio_encoder_model.xml"), device, cpu_cfg
        )
        self.embedder = core.compile_model(
            str(ov_dir / "thinker_embeddings_model.xml"), device, cpu_cfg
        )
        dec_comp = core.compile_model(
            str(ov_dir / "decoder_model.xml"), device, cpu_cfg
        )
        self.dec_req = dec_comp.create_infer_request()

        # 載入 Processor
        print("[INFO] 載入 Processor...")
        from processor_numpy import LightProcessor
        self.processor = LightProcessor(ov_dir)
        self.pad_id = self.processor.pad_id

        # OpenCC 簡→繁
        try:
            self.cc = opencc.OpenCC("s2twp")
        except Exception:
            self.cc = None

        self.ready = True
        print("[INFO] 模型載入完成！")

    def transcribe(self, audio, max_tokens=300, language=None, context=None):
        """轉換音訊為文字"""
        import numpy as np

        if not self.ready:
            raise RuntimeError("模型未載入！")

        # 前處理
        mel, ids = self.processor.prepare(audio, language=language, context=context)

        # 音頻編碼 + 文字 Embedding
        ae = list(self.audio_enc({"mel": mel}).values())[0]
        te = list(self.embedder({"input_ids": ids}).values())[0]

        # 合併
        combined = te.copy()
        mask = ids[0] == self.pad_id
        np_ = int(mask.sum())
        na = ae.shape[1]
        if np_ != na:
            mn = min(np_, na)
            combined[0, np.where(mask)[0][:mn]] = ae[0, :mn]
        else:
            combined[0, mask] = ae[0]

        # Decoder 自回歸生成
        L = combined.shape[1]
        pos = np.arange(L, dtype=np.int64)[np.newaxis, :]
        self.dec_req.reset_state()
        out = self.dec_req.infer({0: combined, "position_ids": pos})
        logits = list(out.values())[0]

        eos = self.processor.eos_id
        eot = self.processor.eot_id
        gen = []
        nxt = int(np.argmax(logits[0, -1, :]))
        cur = L
        while nxt not in (eos, eot) and len(gen) < max_tokens:
            gen.append(nxt)
            emb = list(self.embedder(
                {"input_ids": np.array([[nxt]], dtype=np.int64)}
            ).values())[0]
            out = self.dec_req.infer(
                {0: emb, "position_ids": np.array([[cur]], dtype=np.int64)}
            )
            logits = list(out.values())[0]
            nxt = int(np.argmax(logits[0, -1, :]))
            cur += 1

        # 解碼
        raw = self.processor.decode(gen)
        if "<asr_text>" in raw:
            raw = raw.split("<asr_text>", 1)[1]
        text = raw.strip()

        # 簡→繁轉換
        if self.cc and text:
            text = self.cc.convert(text)

        return text

    def process_file(self, audio_path, output_path=None, language=None,
                    context=None, diarize=False, n_speakers=None,
                    progress_cb=None):
        """處理音檔並輸出 SRT"""
        import librosa

        if not self.ready:
            raise RuntimeError("模型未載入！")

        audio_path = Path(audio_path)
        print(f"[INFO] 處理音檔: {audio_path.name}")

        # 載入音訊
        audio, _ = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)

        # VAD 分段
        print("[INFO] VAD 靜音偵測...")
        vad_groups = detect_speech_groups(audio, self.vad_sess, self.max_chunk_secs)
        if not vad_groups:
            print("[WARN] 找不到語音區段")
            return None

        groups_spk = [(g0, g1, chunk, None) for g0, g1, chunk in vad_groups]

        # 強制切分過長片段
        max_samples = self.max_chunk_secs * SAMPLE_RATE
        enforced = []
        for t0, t1, chunk, spk in groups_spk:
            if len(chunk) <= max_samples:
                enforced.append((t0, t1, chunk, spk))
            else:
                pos = 0
                while pos < len(chunk):
                    piece = chunk[pos: pos + max_samples]
                    if len(piece) < SAMPLE_RATE:
                        break
                    piece_t0 = t0 + pos / SAMPLE_RATE
                    piece_t1 = min(t1, piece_t0 + len(piece) / SAMPLE_RATE)
                    enforced.append((piece_t0, piece_t1, piece, spk))
                    pos += max_samples
        groups_spk = enforced

        # 逐段轉換
        all_subs = []
        total = len(groups_spk)
        print(f"[INFO] 共 {total} 個片段，開始轉換...")

        for i, (g0, g1, chunk, spk) in enumerate(groups_spk):
            if progress_cb:
                progress_cb(i, total, f"[{i+1}/{total}]")

            max_tok = 400 if language == "Japanese" else 300
            text = self.transcribe(chunk, max_tokens=max_tok,
                                   language=language, context=context)
            if not text:
                continue

            lines = split_to_lines(text)
            all_subs.extend(
                (s, e, line, spk) for s, e, line in assign_ts(lines, g0, g1)
            )

            # 即時顯示
            print(f"  [{i+1}/{total}] {text[:50]}{'...' if len(text) > 50 else ''}")

        if not all_subs:
            return None

        # 寫入 SRT
        if output_path is None:
            output_path = audio_path.with_suffix(".srt")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for idx, (s, e, line, spk) in enumerate(all_subs, 1):
                prefix = f"{spk}：" if spk else ""
                f.write(f"{idx}\n{srt_ts(s)} --> {srt_ts(e)}\n{prefix}{line}\n\n")

        print(f"[OK] 已儲存: {output_path}")
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Qwen3-ASR OpenVINO CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python qwen3-asr-ov.py -i audio.mp3 -o output.srt
  python qwen3-asr-ov.py -i audio.mp3 -o output.srt -l Japanese
  python qwen3-asr-ov.py -i "C:/Music" -o "C:/Output"
  python qwen3-asr-ov.py -i audio.mp3 --list-languages

注意:
  模型路徑預設為 D:\\Python\\QwenASR\\ov_models
  如需指定他路徑，請用 --model-dir 參數
        """
    )

    parser.add_argument("-i", "--input", nargs="+", required=True,
                        help="輸入音頻檔案或資料夾")
    parser.add_argument("-o", "--output", default=None,
                        help="輸出 SRT 檔案路徑或資料夾（預設與輸入同目錄）")
    parser.add_argument("-l", "--language", default=None,
                        help=f"語言（預設自動偵測）可用值: {', '.join(LANGUAGES)}")
    parser.add_argument("-m", "--model-dir", default=None,
                        help="模型目錄路徑")
    parser.add_argument("-t", "--threads", type=int, default=0,
                        help="CPU 執行緒數（0=自動）")
    parser.add_argument("--diarize", action="store_true",
                        help="啟用說話者分離")
    parser.add_argument("--speakers", type=int, default=None,
                        help="說話者人數")
    parser.add_argument("--list-languages", action="store_true",
                        help="顯示支援的語言列表")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="顯示詳細資訊")

    args = parser.parse_args()

    if args.list_languages:
        print("支援的語言：")
        for lang in LANGUAGES:
            print(f"  - {lang}")
        return

    # 取得輸入檔案
    input_files = get_audio_files(args.input)
    if not input_files:
        print(f"[ERROR] 找不到音頻檔案: {args.input}")
        sys.exit(1)

    print(f"[INFO] 找到 {len(input_files)} 個檔案")

    # 初始化引擎
    engine = QwenASROpenVINO(
        model_dir=args.model_dir,
        cpu_threads=args.threads
    )

    # 嘗試自動設定路徑
    if args.model_dir is None:
        model_dir = find_qwen_asr_ov()
        if model_dir:
            args.model_dir = model_dir

    print("[INFO] 載入模型...")
    engine.load(device="CPU")

    # 處理每個檔案
    for audio_path in input_files:
        print("-" * 50)
        if args.output and Path(args.output).is_dir():
            output_path = Path(args.output) / audio_path.with_suffix(".srt").name
        elif args.output:
            output_path = args.output
        else:
            output_path = None

        start = time.time()
        try:
            result = engine.process_file(
                audio_path=audio_path,
                output_path=output_path,
                language=args.language,
                diarize=args.diarize,
                n_speakers=args.speakers
            )
            elapsed = time.time() - start
            if result:
                print(f"[完成] {audio_path.name} ({elapsed:.1f}秒)")
        except Exception as e:
            print(f"[ERROR] 處理失敗: {audio_path.name}")
            print(f"        {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    print("-" * 50)
    print("[INFO] 全部完成！")


if __name__ == "__main__":
    main()
