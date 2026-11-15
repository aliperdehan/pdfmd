"""Visible parent metadata layers, their depth and their ordinary build behaviour."""
from __future__ import annotations

import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isolation_support  # noqa: E402,F401
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pdfmd


class Fixture(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.doc = self.write('project/report/doc.md', 'Body\n')
        self.parent = self.write('project/metadata/metadata.yaml', 'author: Parent\n')
        self.far = self.write('metadata/metadata.yaml', 'author: Far\n')
        self.write('.pdfmd/config.yaml', 'inherit: false\n')
        pdfmd.folder_walk.cache_clear()
        self.addCleanup(pdfmd.folder_walk.cache_clear)
        self.env = {**os.environ, 'PDFMD_CONFIG': '', 'PDFMD_NO_PROMPT': '1',
                    'TEXMFVAR': str(self.root / 'tex-var'), 'TEXMFCONFIG': str(self.root / 'tex-config'),
                    **{'XDG_' + key + '_HOME': str(self.root / key.lower()) for key in ('CONFIG', 'CACHE', 'DATA')}}
        env = patch.dict(os.environ, self.env)
        env.start()
        self.addCleanup(env.stop)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def setting(self, value):
        self.doc.write_text('---\npdfmd-options: {metadata-parents: ' + str(value) + '}\n---\nBody\n')

    def found(self, **kwargs):
        found = pdfmd.find_metadata(self.doc.parent, None, document=self.doc, document_stem=self.doc.stem, **kwargs)
        return [] if found is None else found if isinstance(found, list) else [found]


class Discovery(Fixture):
    def test_default_is_one_parent(self):
        self.assertEqual(self.found(), [self.parent])

    def test_zero_disables_parents_but_keeps_local_and_folder_layers(self):
        self.setting(0)
        local = self.write('project/report/metadata/metadata.yaml', 'author: Local\n')
        folder = self.write('project/.pdfmd/metadata.yaml', 'author: Folder\n')
        self.assertEqual(self.found(), [local, folder])

    def test_integer_counts_folders_including_ones_without_metadata(self):
        self.parent.unlink()
        self.assertEqual(self.found(), [])
        self.setting(2)
        self.assertEqual(self.found(), [self.far])

    def test_all_and_any_negative_integer_stop_at_the_folder_boundary(self):
        for value in ('all', -1, -7, 2):
            with self.subTest(value=value):
                self.setting(value)
                self.assertEqual(self.found(), [self.parent, self.far])

    def test_inherit_false_in_the_document_folder_stops_parents(self):
        self.write('project/report/.pdfmd/config.yaml', 'inherit: false\n')
        self.assertEqual(self.found(), [])

    def test_boundary_parent_is_included_but_nothing_above_it(self):
        self.setting('all')
        self.write('project/.pdfmd/config.yaml', 'inherit: false\n')
        self.assertEqual(self.found(), [self.parent])

    def test_local_then_folder_then_global_options_control_depth(self):
        self.parent.unlink()
        local = self.write('project/report/metadata.yaml', 'pdfmd-options: {metadata-parents: 2}\n')
        self.assertEqual(self.found(), [local, self.far])
        local.unlink()
        self.write('project/report/.pdfmd/config.yaml', 'options: {metadata-parents: 2}\n')
        pdfmd.folder_walk.cache_clear()
        self.assertEqual(self.found(), [self.far])
        self.write('project/report/.pdfmd/config.yaml', 'options: {}\n')
        pdfmd.folder_walk.cache_clear()
        with patch.object(pdfmd, 'config_options', return_value={'metadata-parents': 2}):
            self.assertEqual(self.found(), [self.far])

    def test_front_matter_overrides_local_depth(self):
        local = self.write('project/report/metadata.yaml', 'pdfmd-options: {metadata-parents: all}\n')
        self.setting(1)
        self.assertEqual(self.found(), [local, self.parent])

    def test_same_file_selection_rule_at_each_parent(self):
        named = self.write('project/metadata/doc.yaml', 'author: Named\n')
        self.write('project/metadata/unrelated.yaml', 'author: Unrelated\n')
        self.write('project/metadata/defaults.yaml', 'author: Defaults\n')
        self.write('project/outside.yaml', 'author: Outside\n')
        self.assertEqual(self.found(), [self.parent, named])

    def test_single_yaml_and_report_names_and_ambiguity_follow_local_rule(self):
        self.parent.unlink()
        only = self.write('project/metadata/shared.yml', 'author: Only\n')
        self.assertEqual(self.found(), [only])
        report = self.write('project/metadata/report.yaml', 'author: Report\n')
        self.assertEqual(self.found(report=True), [report])
        with self.assertRaisesRegex(ValueError, 'Multiple YAML files'):
            self.found()

    def test_explicit_and_explicit_only_discovery_keep_their_old_scope(self):
        local = self.write('project/report/metadata.yaml', 'author: Local\n')
        self.assertEqual(pdfmd.find_metadata(self.doc.parent, [str(local)], document=self.doc), [local])
        self.assertIs(pdfmd.find_metadata(self.doc.parent, [], document=self.doc), pdfmd.AUTO_METADATA_DISABLED)
        self.assertEqual(self.found(discover=False), [])

    def test_layers_keep_their_priority_in_both_metadata_precedence_modes_and_workers(self):
        self.setting('all')
        local = self.write('project/report/metadata.yaml', 'author: Local\n')
        named = self.write('project/report/doc.yaml', 'author: Named\n')
        parent_named = self.write('project/metadata/doc.yaml', 'author: ParentNamed\n')
        folder = self.write('project/.pdfmd/metadata.yaml', 'author: Folder\n')
        kit = self.write('kit/defaults.yaml', 'author: Kit\n')
        config = self.write('global/config.yaml', '{}\n')
        global_meta = self.write('global/metadata.yaml', 'author: Global\n')
        with patch.object(pdfmd, 'config_path', return_value=config), patch.dict(pdfmd.KIT_METADATA, {kit: 'test'}):
            found = self.found(kits=False)
            found.insert(-1, kit)
            for mode, expected in (
                ('later', [global_meta, kit, folder, self.far, self.parent, parent_named, local, named]),
                ('first', [global_meta, kit, folder, self.far, parent_named, self.parent, named, local]),
            ):
                with self.subTest(mode=mode), patch.object(pdfmd, 'METADATA_PRECEDENCE_CLI', mode):
                    self.assertEqual(pdfmd.pandoc_metadata_order(found), expected)
                    restored = pickle.loads(pickle.dumps(found))
                    self.assertEqual(pdfmd.pandoc_metadata_order(restored), expected)
                    self.assertEqual(pdfmd.metadata_files_by_priority(found), list(reversed(expected)))

    def test_a_parent_file_can_be_local_to_another_build_without_stale_layer_state(self):
        inherited = self.found()
        other = self.write('project/other.md', 'Body\n')
        found = pdfmd.find_metadata(other.parent, None, document=other, document_stem=other.stem)
        files = found if isinstance(found, list) else [found]
        self.assertEqual(inherited, [self.parent])
        from pdfmd_metadata import is_parent_metadata
        self.assertTrue(is_parent_metadata(inherited[0]))
        self.assertFalse(is_parent_metadata(files[0]))

    def test_a_parent_setting_does_not_extend_its_own_discovery(self):
        self.parent.write_text('pdfmd-options: {metadata-parents: all}\n')
        self.assertEqual(self.found(), [self.parent])

    def test_bad_depth_is_reported_without_silently_changing_discovery(self):
        for value in ('nonsense', '1.5', 'true'):
            with self.subTest(value=value):
                self.setting(value)
                with self.assertRaisesRegex(SystemExit, 'metadata-parents'):
                    self.found()

    def test_setup_row_is_available_globally_and_per_folder(self):
        from pdfmd_setup.registry import settings_for, folder_split
        SETTINGS = settings_for(pdfmd.NO_AUTO_KINDS)
        from pdfmd_setup.inventory import OPTIONS
        from pdfmd_setup.plain import edit
        row = next(row for row in SETTINGS if row.key == 'options.metadata-parents')
        self.assertIn(row, folder_split(SETTINGS)[0])
        self.assertTrue(row.unset)
        self.assertEqual(OPTIONS['metadata-parents'], row.key)
        for value in ('0', '2', 'all', '-7'):
            with self.subTest(value=value):
                stores = {'config': {}, 'metadata': {}}
                edit(stores, row, lambda _: value, lambda _: None)
                with patch.object(pdfmd, 'config_options', return_value=stores['config']['options']):
                    self.assertEqual(self.found(), [] if value == '0' else [self.parent, self.far])


@unittest.skipUnless(shutil.which('pandoc'), 'needs Pandoc')
class Builds(Fixture):
    # Keep the integration cases separate from the discovery assertions.
    def build(self, *args, source=None, target='html', ok=True):
        output = self.root / ('result.' + ('tex' if target == 'latex' else target))
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), str(source or self.doc), '--to', target,
                               '-o', str(output), '--standalone', '--no-backup', '--no-stamp', '--no-auto', 'font', *args],
                              cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0 if ok else 1, done.stdout + done.stderr)
        return output.read_text(), done.stdout + done.stderr

    def test_percent_title_parent_author_verbose_and_off_switches(self):
        self.doc.write_text('% DocumentTitle\n\nBody\n')
        text, log = self.build('--verbose')
        self.assertIn('DocumentTitle', text)
        self.assertIn('Parent', text)
        self.assertIn('AUTO', log)
        self.assertIn('YAML', log)
        self.assertIn('project/metadata/metadata.yaml', log)
        for args in (('--no-auto', 'metadata'), ('-y',)):
            with self.subTest(args=args):
                text, _ = self.build(*args)
                self.assertNotIn('Parent', text)
        self.setting(0)
        text, _ = self.build()
        self.assertNotIn('Parent', text)

    def test_command_front_matter_local_parent_folder_kit_global_precedence(self):
        self.doc.write_text('---\ntitle: T\n---\nBody\n')
        self.write('global/metadata.yaml', 'author: Global\n')
        config = self.write('global/config.yaml', 'kits: [' + str(self.root / 'project/report/kits/lab') + ']\n')
        self.env['PDFMD_CONFIG'] = str(config)
        self.write('project/report/kits/lab/.kit', 'kit-format: 1\nname: lab\ndefaults: defaults.yaml\n')
        self.write('project/report/kits/lab/defaults.yaml', 'author: Kit\n')
        self.write('project/report/.pdfmd/config.yaml', 'options: {kit: lab}\n')
        folder = self.write('project/report/.pdfmd/metadata.yaml', 'author: Folder\n')
        local = self.write('project/report/metadata.yaml', 'author: Local\n')
        self.assertIn('Local', self.build()[0])
        self.doc.write_text('---\ntitle: T\nauthor: Front\n---\nBody\n')
        self.assertIn('Front', self.build()[0])
        self.assertIn('Command', self.build('-M', 'author=Command')[0])
        self.doc.write_text('---\ntitle: T\n---\nBody\n')
        for path, winner in ((local, 'Parent'), (self.parent, 'Folder'), (folder, 'Kit')):
            path.unlink()
            self.assertIn(winner, self.build()[0])
        self.write('project/report/.pdfmd/config.yaml', 'options: {}\n')
        self.assertIn('Global', self.build()[0])

    def test_parent_resources_and_named_filters_and_preambles_keep_relative_paths(self):
        self.doc.write_text('% Title\n\nOriginal. Cite @key.\n')
        self.parent.write_text('bibliography: refs.bib\npdfmd-options:\n  lua-filter: assets/change.lua\n  preamble: assets/extra.tex\n')
        style = subprocess.run([shutil.which('pandoc'), '--print-default-data-file', 'default.csl'],
                               env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True).stdout
        self.write('project/metadata/parent.csl', style)
        self.parent.write_text('csl: parent.csl\n' + self.parent.read_text())
        self.write('project/metadata/refs.bib', '@book{key, author={Writer, A}, title={ParentReference}, year={2000}}\n')
        self.write('project/metadata/assets/change.lua',
                   'function Str(s) if s.text == "Original." then s.text = "Changed" end return s end\n')
        self.write('project/metadata/assets/extra.tex', '\\newcommand{\\ParentPreamble}{yes}\n')
        text, log = self.build()
        self.assertIn('ParentReference', text)
        self.assertIn('Changed', text)
        self.assertIn('is new here; it runs', log)
        text, _ = self.build(target='latex')
        self.assertIn('\\ParentPreamble', text)
        # The same resource path must work when local metadata fixes a different cwd.
        self.write('project/report/metadata/metadata.yaml', 'subtitle: Local\n')
        self.assertIn('ParentReference', self.build()[0])

    def test_scaffold_and_part_count_from_scaffold_not_from_parts(self):
        self.doc.write_text('---\ntitle: Scaffold\npdfmd-options: {parts: auto}\n---\n')
        part = self.write('project/report/parts/nested/01.md', '# Section\n\nBody\n')
        self.write('project/report/metadata/metadata.yaml', 'subtitle: Local\n')
        # This would be the wrong parent layer if counted from the part folder.
        self.write('project/report/parts/metadata/metadata.yaml', 'author: WrongPartParent\n')
        for source in (self.doc, part):
            with self.subTest(source=source):
                text, _ = self.build(source=source)
                self.assertIn('Parent', text)
                self.assertNotIn('WrongPartParent', text)

    def test_show_config_names_the_discovered_layers_even_without_global_config(self):
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), str(self.doc), '--show-config'],
                              cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('project/metadata/metadata.yaml', done.stdout)

    def test_show_config_honours_explicit_metadata_and_off_switches(self):
        explicit = self.write('explicit.yaml', 'author: Explicit\n')
        for args, expected in ((('-y', str(explicit)), True), (('-y',), False), (('--no-auto', 'metadata'), False)):
            with self.subTest(args=args):
                done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), str(self.doc), '--show-config', *args],
                                      cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertNotIn('project/metadata/metadata.yaml', done.stdout)
                self.assertEqual('explicit.yaml' in done.stdout, expected)

    def test_parent_automatically_named_preamble_and_filter_use_existing_safety_rules(self):
        self.doc.write_text('% Title\n\nOriginal\n')
        self.write('project/metadata/doc.lua',
                   'function Str(s) if s.text == "Original" then s.text = "AutoChanged" end return s end\n')
        self.write('project/metadata/unrelated.lua', 'error("must not run")\n')
        self.write('project/metadata/preamble.tex', '\\newcommand{\\ParentAuto}{yes}\n')
        text, log = self.build('--strict', ok=False)
        self.assertIn('Original', text)
        self.assertNotIn('AutoChanged', text)
        self.assertIn('doc.lua', log)
        text, log = self.build()
        self.assertIn('AutoChanged', text)
        self.assertIn('is new here; it runs', log)
        text, _ = self.build(target='latex')
        self.assertIn('\\ParentAuto', text)
        text, _ = self.build('--no-auto', 'preamble', target='latex')
        self.assertNotIn('\\ParentAuto', text)

    @unittest.skipUnless(shutil.which('typst'), 'needs Typst')
    def test_parent_engine_and_author_in_a_real_pdf(self):
        self.doc.write_text('% DocumentTitle\n\nBody\n')
        self.parent.write_text('author: ParentAuthor\npdfmd-options: {engine: typst, shrink: false}\n')
        output = self.root / 'real.pdf'
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), str(self.doc), '-o', str(output),
                               '--no-backup', '--no-stamp', '--no-attach-source', '--no-auto', 'font', '--verbose'],
                              cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(output.read_bytes().startswith(b'%PDF'))
        self.assertIn('typst', done.stdout)
        from pypdf import PdfReader
        text = ''.join(page.extract_text() for page in PdfReader(output).pages)
        self.assertIn('DocumentTitle', text)
        self.assertIn('ParentAuthor', text)

    def test_batch_workers_keep_parent_layers_below_each_documents_local_metadata(self):
        self.doc.write_text('% First\n\nBody\n')
        self.write('project/report/second.md', '% Second\n\nBody\n')
        self.write('project/report/metadata.yaml', 'subtitle: SharedLocal\n')
        self.write('project/report/second.yaml', 'author: LocalSecond\n')
        done = subprocess.run([sys.executable, str(ROOT / 'scripts/pdfmd'), str(self.doc.parent), '-b', '-j', '2',
                               '--to', 'html', '--standalone', '--no-backup', '--no-stamp', '--no-auto', 'font'],
                              cwd=self.root, env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('Parent', self.doc.with_suffix('.html').read_text())
        self.assertIn('LocalSecond', (self.doc.parent / 'second.html').read_text())
