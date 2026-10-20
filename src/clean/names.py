"""Normalisation helpers to match the same organisation across sources
(startup registry, patent applicants, Polimi spin-off pages)."""
import re
import unicodedata

# Legal forms and qualifiers removed before comparing names
LEGAL_FORMS = re.compile(
    r"\b(s ?r ?l ?s?|s ?p ?a|s ?a ?s|s ?n ?c|soc(ieta)? (a )?responsabilita limitata( semplificata)?|"
    r"societa per azioni|societa benefit|sb|start ?up costituita.*|in liquidazione|"
    r"spin ?off (de|del|of) politecnico di milano|ltd|limited|inc|corp|gmbh|bv|nv)\b"
)


def org_key(name):
    """'ARTINESS S.R.L.' -> 'artiness'; "Pionirs S.r.l." -> 'pionirs'."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = LEGAL_FORMS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def domain_key(url):
    """'https://www.pionirs.com/en' -> 'pionirs.com'."""
    url = str(url).strip().lower()
    if not url:
        return ""
    url = re.sub(r"^[a-z]+://", "", url).split("/")[0]
    return re.sub(r"^www\d?\.", "", url)
