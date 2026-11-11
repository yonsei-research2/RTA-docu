"""HTML helpers used by the single-page publisher."""
import argparse
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
from urllib.parse import quote, urlsplit

DIRECT_PATH = "직접 경로 입력"
NOTICE = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width,initial-scale=1">'
          '<meta name="robots" content="noindex,nofollow"><title>페이지 안내</title>'
          '</head><body><p>개별 링크로 접속해 주세요.</p></body></html>')


def html_files(source):
    return sorted((p.relative_to(source) for p in source.rglob('*')
                   if p.is_file() and p.suffix.lower() in {'.html', '.htm'}),
                  key=lambda p: p.as_posix().casefold())


class HeadParser(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.lines = text.splitlines(keepends=True)
        self.head = self.html = self.doctype = None
        self.base = None
        self.template_depth = 0
        self.feed(text)

    def absolute_offset(self):
        line, column = self.getpos()
        return sum(len(s) for s in self.lines[:line - 1]) + column

    def handle_starttag(self, tag, attrs):
        if tag == 'template':
            self.template_depth += 1
        if self.template_depth:
            return
        end = self.absolute_offset() + len(self.get_starttag_text())
        if tag == 'head' and self.head is None:
            self.head = end
        if tag == 'html' and self.html is None:
            self.html = end
        if tag == 'base' and self.base is None:
            attrs = dict(attrs)
            if attrs.get('href') is not None:
                self.base = attrs['href']

    def handle_endtag(self, tag):
        if tag == 'template':
            self.template_depth = max(0, self.template_depth - 1)

    def handle_decl(self, decl):
        if decl.lower().startswith('doctype') and self.doctype is None:
            self.doctype = self.absolute_offset() + len(decl) + 3


def clean_copy(text, original_name, original_href=None):
    """Keep relative CSS, images and fetch() requests at the original location."""
    parser = HeadParser(text)
    old_document = original_href or ('../' + quote(original_name, safe=''))
    href = old_document
    if parser.base is not None:
        existing = parser.base.strip()
        if existing.startswith('/') or urlsplit(existing).scheme:
            href = existing
        elif not existing or existing.startswith(('?', '#')):
            href = old_document + existing
        else:
            href = old_document.rsplit('/', 1)[0] + '/' + existing
    base = '<base href="' + escape(href, quote=True) + '">'
    if parser.head is not None:
        pos, insert = parser.head, base
    else:
        pos = parser.html if parser.html is not None else (parser.doctype or 0)
        insert = '<head>' + base + '</head>'
    return text[:pos] + insert + text[pos:]
