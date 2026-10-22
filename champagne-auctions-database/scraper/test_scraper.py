"""Test isolato del wrapper HTMLParser per verificare i selettori CSS chiave."""

# Import diretto dal modulo scraper (funziona perché siamo nella stessa cartella)
from scraper import HTMLParser

# --- TEST 1: script#__NEXT_DATA__ ---
html_test = '''
<html>
<body>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"lot": {"title": "Test Champagne"}}}}
</script>
</body>
</html>
'''

parser = HTMLParser(html_test)
node = parser.css_first('script#__NEXT_DATA__')

if node:
    print("✅ Test 1 PASSED - Nodo trovato")
    print(f"   Contenuto: {node.text()[:60]}...")
else:
    print("❌ Test 1 FAILED - Nodo non trovato")

# --- TEST 2: lot-bid-status-section (per il fix del bug .html) ---
html_bid = '''
<div data-testid="lot-bid-status-section">
  <span>Final bid: €1200</span>
  <span>CLOSED</span>
</div>
'''

parser2 = HTMLParser(html_bid)
bid_section = parser2.css_first('[data-testid="lot-bid-status-section"]')

if bid_section:
    print("\n✅ Test 2a PASSED - Sezione bid trovata")
    print(f"   Testo: {bid_section.text().strip()[:60]}")
    # Test critico: .html (bug #2 del review precedente)
    try:
        html_content = bid_section.html
        print(f"✅ Test 2b PASSED - .html funziona: {html_content[:60]}...")
    except AttributeError as e:
        print(f"❌ Test 2b FAILED - .html non implementato: {e}")
else:
    print("\n❌ Test 2 FAILED")

# --- TEST 3: css() con lista multipla ---
html_multi = '<div><span>uno</span><span>due</span><span>tre</span></div>'
parser3 = HTMLParser(html_multi)
nodes = parser3.css('span')
print(f"\n{'✅' if len(nodes) == 3 else '❌'} Test 3 - Trovati {len(nodes)} span (atteso: 3)")

# --- TEST 4: attributes ---
html_attr = '<a href="/l/12345-champagne" class="c-lot-card">Link</a>'
parser4 = HTMLParser(html_attr)
link = parser4.css_first('a.c-lot-card')
if link:
    href = link.attributes.get('href')
    print(f"{'✅' if href == '/l/12345-champagne' else '❌'} Test 4 - href estratto: {href}")