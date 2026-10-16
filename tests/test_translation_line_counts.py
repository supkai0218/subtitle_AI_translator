"""Regression coverage for multiline SRT cues and automatic translation writes.

Run with: python -m unittest discover -s tests -v
"""

import ast
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from modules.ai_validator import TranslationValidator
from modules.srt_separator import SrtSeparator


def load_auto_translation(translator):
    # Exercise the actual worker method without requiring a Qt installation or GUI.
    source = Path(__file__).resolve().parents[1] / 'ai-translator-main.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    method = next(
        method for cls in tree.body if isinstance(cls, ast.ClassDef)
        for method in cls.body
        if isinstance(method, ast.FunctionDef) and method.name == 'run_2C_auto_translation'
    )
    from modules.ai_validator import ValidationStatus
    namespace = {
        'Path': Path,
        'AITranslator': Mock(return_value=translator),
        'TranslationValidator': TranslationValidator,
        'ValidationStatus': ValidationStatus,
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['run_2C_auto_translation']


class TranslationLineCountTests(unittest.TestCase):
    def test_521_cues_with_multiline_text_stay_521_txt_lines(self):
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'sample.srt'
                blocks = []
                for index in range(1, 522):
                    text = 'first line\nsecond line' if index <= 12 else 'single line'
                    blocks.append(f'{index}\n00:00:00,000 --> 00:00:01,000\n{text}')
                source.write_bytes(('\n\n'.join(blocks) + '\n\n').replace('\n', newline).encode('utf-8'))
                separator = SrtSeparator()
                timecodes, subtitles = separator.parse_srt(source)
                text_file, time_file = separator.save_files(timecodes, subtitles, directory, 'sample')
                text_lines = Path(text_file).read_text(encoding='utf-8').splitlines()
                time_lines = Path(time_file).read_text(encoding='utf-8').splitlines()
                self.assertEqual(len(text_lines), 521)
                self.assertEqual(len(time_lines), 521)
                self.assertEqual(text_lines[0], '1:first line second line')
                self.assertEqual(text_lines[-1], '521:single line')
                self.assertEqual([line.split(':', 1)[0] for line in text_lines],
                                 [line.split(':', 1)[0] for line in time_lines])

    def run_worker(self, responses, max_retries, existing_output=None, threshold=0.01):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / 'AI').mkdir()
        (root / '2B').mkdir()
        lines = '\n'.join(f'{i}:source' for i in range(1, 522))
        (root / 'AI' / '1A-txt_sample.txt').write_text(lines, encoding='utf-8')
        target = root / '2B' / '2B-txt_sample.txt'
        if existing_output is not None:
            target.write_text(existing_output, encoding='utf-8')
        translator = Mock()
        translator.validate_api_connection.return_value = (True, 'OK')
        translator.translate_batch.side_effect = [(True, response, '') for response in responses]
        worker = SimpleNamespace(
            base_path=root,
            settings={'ai': 'AI', 'txt_2B': '2B'},
            output_filename='sample',
            main_window=SimpleNamespace(settings={'ai_translation': {
                'max_retries': max_retries, 'retry_delay': 0, 'empty_threshold': threshold,
            }}),
            progress_updated=SimpleNamespace(emit=Mock()),
            log=Mock(),
            msleep=Mock(),
        )
        method = load_auto_translation(translator)
        return lambda: method(worker), translator, target

    def test_valid_response_writes_exactly_521_translations(self):
        response = '\n'.join(f'{i}:translated' for i in range(1, 522))
        run, translator, target = self.run_worker([response], max_retries=0)
        run()
        self.assertEqual(target.read_text(encoding='utf-8'), response)
        self.assertEqual(translator.translate_batch.call_count, 1)

    def test_validation_failure_retries_and_preserves_existing_output(self):
        run, translator, target = self.run_worker(['1:translated'] * 3, max_retries=2,
                                                  existing_output='existing translation')
        with self.assertRaisesRegex(Exception, 'AI 翻譯驗證失敗'):
            run()
        self.assertEqual(translator.translate_batch.call_count, 3)
        self.assertEqual(target.read_text(encoding='utf-8'), 'existing translation')

    def test_zero_retries_does_not_write_invalid_translation(self):
        run, translator, target = self.run_worker(['1:translated'], max_retries=0)
        with self.assertRaisesRegex(Exception, 'AI 翻譯驗證失敗'):
            run()
        self.assertEqual(translator.translate_batch.call_count, 1)
        self.assertFalse(target.exists())

    def test_retry_can_recover_and_write_complete_response(self):
        response = '\n'.join(f'{i}:translated' for i in range(1, 522))
        run, translator, target = self.run_worker(['1:translated', response], max_retries=1)
        run()
        self.assertEqual(translator.translate_batch.call_count, 2)
        self.assertEqual(target.read_text(encoding='utf-8'), response)

    def test_configured_small_empty_translation_allowance_is_preserved(self):
        response = '\n'.join(f'{i}:translated' for i in range(1, 521))
        run, translator, target = self.run_worker([response], max_retries=0)
        run()
        lines = target.read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 521)
        self.assertEqual(lines[-1], '521:')
        self.assertEqual(translator.translate_batch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
