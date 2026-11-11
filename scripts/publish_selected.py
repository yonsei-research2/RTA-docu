"""Publish only the chosen HTML, retaining snapshots of earlier publications."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import shutil
from urllib.parse import quote
from build_pages import NOTICE, clean_copy


def select_path(typed):
    selected = typed.strip()
    if not selected or selected.rstrip('/') == 'public':
        raise ValueError('public/ 뒤에 파일명을 입력하세요. 예: public/test1.html')
    path = PurePosixPath(selected)
    if path.is_absolute() or '..' in path.parts or '\\' in selected or any(ord(c) < 32 for c in selected):
        raise ValueError('public/ 안의 상대 HTML 경로를 입력하세요.')
    if not path.parts or path.parts[0] != 'public' or len(path.parts) < 2:
        raise ValueError('경로는 public/으로 시작해야 합니다.')
    if path.suffix == '':                      # 추가: public/test1 → public/test1.html
        path = path.with_suffix('.html')
    if path.suffix.lower() not in {'.html', '.htm'}:
        raise ValueError(f'HTML 파일만 선택할 수 있습니다. 입력값: {selected}')
    return Path(*path.parts[1:])


def publish(source, archive, rel):
    source, archive = source.resolve(), archive.resolve()
    if source == archive or source in archive.parents or archive in source.parents:
        raise ValueError('원본 폴더와 게시 보관 폴더는 분리되어야 합니다.')
    if rel.is_absolute() or '..' in rel.parts or rel.suffix.lower() not in {'.html','.htm'}:
        raise ValueError('유효하지 않은 HTML 경로입니다.')
    chosen = source / rel
    if not chosen.is_file():
        raise ValueError(f'파일을 찾을 수 없습니다: public/{rel.as_posix()}')
    entries = list(source.rglob('*'))
    if any(p.is_symlink() for p in entries):
        raise ValueError('public/의 심볼릭 링크는 지원하지 않습니다.')
    site = archive / 'site'
    registry_file = archive / 'registry.json'
    if not site.is_dir() or not registry_file.is_file():
        raise ValueError('published-pages 브랜치의 site/와 registry.json이 필요합니다.')
    registry = json.loads(registry_file.read_text())
    slug = rel.with_suffix('').as_posix()
    if slug.split('/')[0] == '_page-assets':
        raise ValueError('_page-assets는 게시용 예약 경로입니다.')
    owner = 'public/' + rel.as_posix()
    if slug in registry and registry[slug] != owner:
        raise ValueError('기존 페이지와 주소가 겹칩니다. HTML 파일명을 바꿔 주세요.')
    dest = site / slug / 'index.html'
    if dest.exists() and slug not in registry:
        raise ValueError('기존 게시 파일과 주소가 겹칩니다.')
    if any(p.is_file() for p in dest.parents if p != site.parent):
        raise ValueError('기존 게시 파일과 폴더 경로가 겹칩니다.')
    text = chosen.read_text(encoding='utf-8-sig')
    # Keep each page's assets separate so another publication cannot change them.
    bundle_rel = Path('_page-assets') / hashlib.sha256(owner.encode()).hexdigest()[:20]
    bundle = site / bundle_rel
    assets = [p for p in entries if p.is_file() and p.suffix.lower() not in {'.html','.htm'}
              and not any(part.startswith('.') for part in p.relative_to(source).parts)]
    old_size = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    new_size = sum(p.stat().st_size for p in assets) + len(text.encode('utf-8')) * 3 + 4096
    if old_size + new_size > 1_000_000_000:
        raise ValueError('사이트 크기가 1 GB 제한에 근접했습니다.')
    if bundle.exists():
        shutil.rmtree(bundle)
    for p in assets + [chosen]:
        target = bundle / p.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    target_document = (bundle_rel / rel).as_posix()
    href = quote(posixpath.relpath(target_document, slug), safe='/')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean_copy(text, rel.name, href), encoding='utf-8')
    # Maintain older direct HTML links, if they were published before migration.
    legacy = site / rel
    if legacy.is_file():
        parent = rel.parent.as_posix()
        legacy_href = quote(posixpath.relpath(target_document, parent), safe='/')
        if '/' not in legacy_href:
            legacy_href = './' + legacy_href
        legacy.write_text(clean_copy(text, rel.name, legacy_href), encoding='utf-8')
    if not (site/'index.html').exists():
        (site/'index.html').write_text(NOTICE, encoding='utf-8')
    registry[slug] = owner
    registry_file.write_text(json.dumps(registry, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return {'file':owner, 'route':slug+'/', 'label':rel.stem}


def result_url(result, base_url):
    if not base_url.startswith(('https://','http://')):
        raise ValueError('Pages 기본 주소가 없습니다.')
    return base_url.rstrip('/') + '/' + quote(result['route'], safe='/')


def summary(result, base_url):
    url = result_url(result, base_url)
    return '## 이용자에게 전달할 결과 링크\n\n' + url + '\n'


if __name__ == '__main__':
    if os.environ.get('WRITE_SUMMARY') == 'true':
        result=json.loads(Path('page-result/result.json').read_text())
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:
            f.write(summary(result, os.environ['PAGE_URL']))
    else:
        rel=select_path(os.environ.get('INPUT_PATH',''))
        result=publish(Path('public'),Path('_published'),rel)
        Path('page-result').mkdir(exist_ok=True)
        Path('page-result/result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            f.write('page_url='+result_url(result,os.environ['PAGE_URL'])+'\n')
        print('Selected page prepared. Previously published pages retained.')
