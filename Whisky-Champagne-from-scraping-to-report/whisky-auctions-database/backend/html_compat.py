"""
html_compat.py - parser HTML senza DLL native, con la stessa API di selectolax.

Perche' esiste
--------------
Su Windows, Smart App Control blocca la DLL nativa di selectolax (lexbor):
"DLL load failed while importing lexbor: Un criterio di controllo
dell'applicazione ha bloccato il file". Quando succede, il backend non parte
nemmeno. Questo modulo usa BeautifulSoup + html.parser, che sono Python puro:
nessuna DLL, niente da bloccare.

Come si usa
-----------
Al posto di:
    from selectolax.parser import HTMLParser
si scrive:
    from html_compat import HTMLParser

Il resto del codice resta identico: tree.css_first(), tree.css(), tree.body,
node.text(), node.html, node.attributes funzionano come in selectolax.

Fedelta' rispetto a selectolax (verificata con test differenziale)
------------------------------------------------------------------
- node.text() concatena TUTTI i nodi di testo discendenti, compreso il
  contenuto dei <script>, senza separatore e senza strip: e' esattamente il
  comportamento di selectolax (e di textContent nel browser). Il get_text()
  standard di BeautifulSoup invece salta il contenuto degli <script> quando
  lo si chiama su un contenitore come <body>: per questo non lo usiamo.
- node.attributes restituisce stringhe anche per "class" (BeautifulSoup di
  default la trasformerebbe in lista).
"""

from bs4 import BeautifulSoup
from bs4.element import (
    NavigableString,
    Comment,
    Declaration,
    Doctype,
    ProcessingInstruction,
    Tag,
)

__all__ = ["HTMLParser", "Node", "BACKEND"]

BACKEND = "bs4/html.parser"

# Tipi di stringa che NON sono nodi di testo nel DOM (commenti, doctype...).
_NON_TEXT = (Comment, Declaration, Doctype, ProcessingInstruction)


def _text_nodes(el):
    """Nodi di testo discendenti, in ordine di documento (come il DOM)."""
    if isinstance(el, NavigableString):
        if not isinstance(el, _NON_TEXT):
            yield str(el)
        return
    for d in el.descendants:
        if isinstance(d, NavigableString) and not isinstance(d, _NON_TEXT):
            yield str(d)


class Node:
    """Nodo con la stessa interfaccia del Node di selectolax."""

    __slots__ = ("_el",)

    def __init__(self, element: Tag):
        self._el = element

    # --- testo -----------------------------------------------------------
    def text(self, deep: bool = True, separator: str = "", strip: bool = False) -> str:
        if deep:
            parts = _text_nodes(self._el)
        else:
            parts = (
                str(c)
                for c in self._el.children
                if isinstance(c, NavigableString) and not isinstance(c, _NON_TEXT)
            )
        if strip:
            return separator.join(p.strip() for p in parts if p.strip())
        return separator.join(parts)

    # --- html / attributi -----------------------------------------------
    @property
    def html(self) -> str:
        return str(self._el)

    @property
    def attributes(self) -> dict:
        return {k: (" ".join(v) if isinstance(v, list) else v) for k, v in self._el.attrs.items()}

    @property
    def attrs(self) -> dict:
        return self.attributes

    @property
    def tag(self) -> str:
        return self._el.name

    @property
    def id(self):
        return self._el.get("id")

    @property
    def parent(self):
        p = self._el.parent
        return Node(p) if isinstance(p, Tag) and p.name != "[document]" else None

    # --- selettori CSS ----------------------------------------------------
    def css_first(self, query: str, default=None, strict: bool = False):
        found = self._el.select_one(query)
        return Node(found) if found is not None else default

    def css(self, query: str):
        return [Node(el) for el in self._el.select(query)]

    def __bool__(self):
        return self._el is not None

    def __repr__(self):
        return f"<Node {self._el.name}>"


class HTMLParser:
    """Documento HTML con la stessa interfaccia di selectolax.parser.HTMLParser."""

    def __init__(self, html):
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        # multi_valued_attributes=None -> "class" resta una stringa, come in selectolax
        self._soup = BeautifulSoup(html, "html.parser", multi_valued_attributes=None)

    def css_first(self, query: str, default=None, strict: bool = False):
        found = self._soup.select_one(query)
        return Node(found) if found is not None else default

    def css(self, query: str):
        return [Node(el) for el in self._soup.select(query)]

    @property
    def body(self):
        b = self._soup.body
        return Node(b) if b is not None else None

    @property
    def head(self):
        h = self._soup.head
        return Node(h) if h is not None else None

    @property
    def root(self):
        r = self._soup.find("html")
        return Node(r) if r is not None else None

    @property
    def html(self) -> str:
        return str(self._soup)

    def text(self, deep: bool = True, separator: str = "", strip: bool = False) -> str:
        return Node(self._soup).text(deep=deep, separator=separator, strip=strip)
