import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urljoin
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_pages import NOTICE, HeadParser, clean_copy
from publish_selected import publish, select_path, summary, result_url

class SelectedPageTests(unittest.TestCase):
    def setup_dirs(self,tmp):
        src=Path(tmp)/'public';archive=Path(tmp)/'archive'
        src.mkdir();(archive/'site').mkdir(parents=True)
        (archive/'site/index.html').write_text(NOTICE)
        (archive/'registry.json').write_text('{}')
        return src,archive

    def test_only_selected_published_and_other_page_snapshot_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,archive=self.setup_dirs(tmp)
            (src/'a.html').write_text('<h1>A</h1>')
            (src/'b.html').write_text('<h1>B</h1>')
            (src/'data.json').write_text('old assets')
            result=publish(src,archive,Path('a.html'))
            self.assertFalse((archive/'site/b').exists())
            self.assertFalse(any(p.name=='b.html' for p in (archive/'site').rglob('*')))
            a_page=(archive/'site/a/index.html').read_bytes()
            a_assets={p.as_posix():p.read_bytes() for p in (archive/'site/_page-assets').rglob('*') if p.is_file()}
            (src/'a.html').write_text('UNPUBLISHED CHANGE')
            (src/'data.json').write_text('new assets')
            publish(src,archive,Path('b.html'))
            self.assertEqual((archive/'site/a/index.html').read_bytes(),a_page)
            for path,content in a_assets.items(): self.assertEqual(Path(path).read_bytes(),content)
            self.assertTrue((archive/'site/b/index.html').exists())
            self.assertEqual((archive/'site/index.html').read_text(),NOTICE)
            report=summary(result,'https://example.org/repo/')
            self.assertEqual(report,'## 이용자에게 전달할 결과 링크\n\nhttps://example.org/repo/a/\n')
            self.assertNotIn('/b/',report)

    def test_republish_updates_only_selected_and_preserves_legacy_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,archive=self.setup_dirs(tmp)
            (archive/'site/a.html').write_text('legacy')
            (src/'a.html').write_text('<h1>first</h1>')
            publish(src,archive,Path('a.html'))
            (src/'a.html').write_text('<h1>second</h1>')
            publish(src,archive,Path('a.html'))
            self.assertIn('second',(archive/'site/a/index.html').read_text())
            self.assertIn('second',(archive/'site/a.html').read_text())
            self.assertEqual(len(json.loads((archive/'registry.json').read_text())),1)

    def test_nested_unicode_assets_resolve_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,archive=self.setup_dirs(tmp)
            (src/'분야').mkdir();(src/'분야/보고서.html').write_text('<head></head><h1>한글</h1>')
            (src/'data.json').write_text('{}')
            result=publish(src,archive,Path('분야/보고서.html'))
            url=result_url(result,'https://example.org/repo/')
            self.assertNotIn('.html',url)
            base=HeadParser((archive/'site/분야/보고서/index.html').read_text()).base
            asset_url=urljoin(urljoin(url,base),'../data.json')
            self.assertIn('/repo/_page-assets/',asset_url)
            self.assertTrue(asset_url.endswith('/data.json'))

    def test_paths_and_missing_files_rejected(self):
        self.assertEqual(select_path(' public/b.html '),Path('b.html'))
        for path in ['', 'public/', '../a.html','public/../a.html','/public/a.html','a.html','public/a.txt','public/a\n.html']:
            with self.assertRaises(ValueError): select_path(path)
        with tempfile.TemporaryDirectory() as tmp:
            src,archive=self.setup_dirs(tmp)
            with self.assertRaises(ValueError):publish(src,archive,Path('missing.html'))

    def test_collision_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,archive=self.setup_dirs(tmp)
            (src/'a.html').write_text('A');(src/'a.htm').write_text('B')
            publish(src,archive,Path('a.html'))
            with self.assertRaises(ValueError):publish(src,archive,Path('a.htm'))
            (src/'link.html').symlink_to(src/'a.html')
            with self.assertRaises(ValueError):publish(src,archive,Path('link.html'))

    def test_existing_base_and_script_content_preserved(self):
        text='<html><head><base href="assets/"><script>const x="<head>";</script></head></html>'
        result=clean_copy(text,'a.html','../_page-assets/id/a.html')
        self.assertEqual(HeadParser(result).base,'../_page-assets/id/assets/')
        self.assertIn('const x="<head>"',result)

if __name__=='__main__':unittest.main()
