"""
citation_verifier.py

Searches academic databases to verify whether a citation is real or hallucinated.
Uses free APIs: Crossref, Semantic Scholar, OpenAlex, and PubMed.

Usage:
    from citation_verifier import CitationVerifier

    verifier = CitationVerifier()
    result = verifier.verify({
        "title": "Attention is all you need",
        "authors": ["Vaswani", "Shazeer"],
        "year": 2017,
        "journal": "Advances in Neural Information Processing Systems"
    })
    print(result)
"""

import time
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    citation: dict
    verdict: str          # "VERIFIED", "LIKELY_REAL", "SUSPICIOUS", "NOT_FOUND"
    confidence: float     # 0.0 – 1.0
    matches: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def __str__(self):
        lines = [
            f"Verdict   : {self.verdict}  (confidence={self.confidence:.0%})",
            f"Title     : {self.citation.get('title', 'N/A')}",
        ]
        for m in self.matches:
            lines.append(f"  ✔ {m['source']}: {m.get('url', m.get('doi', ''))}")
        for n in self.notes:
            lines.append(f"  {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 10) -> Optional[dict]:
    """Simple HTTP GET that returns parsed JSON or None."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CitationVerifier/1.0 (academic research tool)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation for fuzzy comparison."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _title_similarity(a: str, b: str) -> float:
    """Token overlap ratio between two titles."""
    sa = set(_normalize(a).split())
    sb = set(_normalize(b).split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


def _author_match(citation_authors: list[str], result_authors: list[str]) -> str:
    """True if at least one author surname appears in the result list."""
    verdict = ""

    norm_result = [_normalize(a) for a in result_authors]
    norm_citation = [_normalize(a) for a in citation_authors]
    result_authors_surname = [a.split()[-1] for a in norm_result]
    citation_authors_surname = [a.split()[-1] for a in norm_citation]

    if citation_authors_surname == result_authors_surname:
        verdict = "FULL MATCH"
        return verdict
    
    ##Build code to check for differences and return differences in verdict var
    for i in range(len(citation_authors_surname)):
        if citation_authors_surname[i] != result_authors_surname[i]:
            verdict += f"Author mismatch: expected '{citation_authors_surname[i]}', found '{result_authors_surname[i]}'. "
    return verdict.strip()


# ---------------------------------------------------------------------------
# Individual database searchers
# ---------------------------------------------------------------------------

class CrossrefSearcher:
    BASE = "https://api.crossref.org/works"

    def search(self, citation: dict) -> list[dict]:
        title = citation.get("title", "")
        params = urllib.parse.urlencode({
            "query.title": title,
            "rows": 5,
            "select": "DOI,title,author,published,container-title",
        })
        data = _get(f"{self.BASE}?{params}")
        if not data:
            return []

        results = []
        for item in data.get("message", {}).get("items", []):
            candidate_title = " ".join(item.get("title", [""]))
            sim = _title_similarity(title, candidate_title)
            if sim < 0.5:
                continue

            # Extract year
            date_parts = (
                item.get("published", {})
                    .get("date-parts", [[None]])[0]
            )
            year = date_parts[0] if date_parts else None

            # Extract authors
            authors = [
                a.get("family", "") for a in item.get("author", [])
            ]

            results.append({
                "source": "Crossref",
                "title": candidate_title,
                "authors": authors,
                "year": year,
                "journal": " / ".join(item.get("container-title", [])),
                "doi": item.get("DOI", ""),
                "url": f"https://doi.org/{item.get('DOI', '')}",
                "similarity": sim,
            })
        return results


class SemanticScholarSearcher:
    BASE = "https://api.semanticscholar.org/graph/v1/paper/search"

    def search(self, citation: dict) -> list[dict]:
        title = citation.get("title", "")
        params = urllib.parse.urlencode({
            "query": title,
            "limit": 5,
            "fields": "title,authors,year,venue,externalIds,openAccessPdf",
        })
        data = _get(f"{self.BASE}?{params}")
        if not data:
            return []

        results = []
        for item in data.get("data", []):
            candidate_title = item.get("title", "")
            sim = _title_similarity(title, candidate_title)
            if sim < 0.5:
                continue

            authors = [a.get("name", "") for a in item.get("authors", [])]
            doi = item.get("externalIds", {}).get("DOI", "")
            s2_id = item.get("paperId", "")

            results.append({
                "source": "Semantic Scholar",
                "title": candidate_title,
                "authors": authors,
                "year": item.get("year"),
                "journal": item.get("venue", ""),
                "doi": doi,
                "url": (
                    f"https://doi.org/{doi}" if doi
                    else f"https://www.semanticscholar.org/paper/{s2_id}"
                ),
                "similarity": sim,
            })
        return results


class OpenAlexSearcher:
    BASE = "https://api.openalex.org/works"

    def search(self, citation: dict) -> list[dict]:
        title = citation.get("title", "")
        params = urllib.parse.urlencode({
            "search": title,
            "per-page": 5,
            "select": "id,title,authorships,publication_year,primary_location,doi",
        })
        data = _get(f"{self.BASE}?{params}")
        if not data:
            return []

        results = []
        for item in data.get("results", []):
            candidate_title = item.get("title", "") or ""
            sim = _title_similarity(title, candidate_title)
            if sim < 0.5:
                continue

            authors = [
                a.get("author", {}).get("display_name", "")
                for a in item.get("authorships", [])
            ]
            doi = (item.get("doi") or "").replace("https://doi.org/", "")
            journal = (
                (item.get("primary_location") or {})
                .get("source", {}) or {}
            ).get("display_name", "")

            results.append({
                "source": "OpenAlex",
                "title": candidate_title,
                "authors": authors,
                "year": item.get("publication_year"),
                "journal": journal,
                "doi": doi,
                "url": item.get("doi") or item.get("id", ""),
                "similarity": sim,
            })
        return results


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------

SEARCHERS = [
    CrossrefSearcher(),
    SemanticScholarSearcher(),
    OpenAlexSearcher()
]


class CitationVerifier:
    """
    Verify a citation dict with keys:
        title (str)          – required
        authors (list[str])  – optional but improves accuracy
        year (int|str)       – optional
        journal (str)        – optional
    """

    def __init__(self, rate_limit_delay: float = 0.5):
        self.delay = rate_limit_delay

    def verify(self, citation: dict) -> VerificationResult:
        title   = citation.get("title", "")
        authors = [citation.get("authors", [])] if type(citation.get("authors", [])) == str else citation.get("authors", [])
        year    = str(citation.get("publication_date", "")) if citation.get("publication_date") else ""
        journal = citation.get("journal", "")

        print(f"Verifying: {title} | Authors: {authors} | Year: {year} | Journal: {journal}")
        all_matches: list[dict] = []
        notes: list[str] = []

        ##Search each database, but if we find an exact title match, skip the rest to save time and API calls
        exact_match_found = False
        for searcher in SEARCHERS:
            try:
                hits = searcher.search(citation)
                print(f"  {searcher.__class__.__name__} found {len(hits)} hits.")
                all_matches.extend(hits)
                if not exact_match_found:
                    for hit in hits:
                        if hit["similarity"] == 1.0:
                            print(f"  Exact match found in {hit['source']}, skipping other searchers.")
                            all_matches = [hit]  # Keep only the exact match
                            exact_match_found = True
                            break
            except Exception as e:
                notes.append(f"{searcher.__class__.__name__} error: {e}")
            if exact_match_found:
                    break
            time.sleep(self.delay)

        # Score each match
        best_score = 0.0
        best_matches: list[dict] = []


        for m in all_matches:
            score = m["similarity"]  # title similarity 0-1


            if score == 1.0:
                notes.append(f"Exact title match found in {m['source']}.")
            else:
                notes.append(f"Partial title match in {m['source']} with similarity {score:.0%}. Expected title: '{title}', found: '{m['title']}'.")
            #Fix author to incorporate new author match function
            if authors:
                 author_verdict = _author_match(authors, m.get("authors", []))
                 if author_verdict == "FULL MATCH":
                    score = min(1.0, score + 0.25)
                    notes.append(f"Author full match ({m['source']})")
                 elif author_verdict.startswith("Author mismatch"):
                    score = max(0.0, score - 0.15)
                    notes.append(
                        f"{author_verdict} ({m['source']})"
                    )

            # Year match
            if year and str(m.get("year", "")) == year:
                score = min(1.0, score + 0.1)
                notes.append(f"Year match ({m['source']}): {year}")
            elif year and m.get("year") and str(m.get("year")) != year:
                score = max(0.0, score - 0.1)
                notes.append(
                    f"Year mismatch ({searcher.__class__.__name__}): "
                    f"expected {year}, found {m['year']}"
                )

            """
            # Journal bonus (loose)
            if journal and m.get("journal"):
                j_sim = _title_similarity(journal, m["journal"])
                if j_sim > 0.4:
                    score = min(1.0, score + 0.1)
            """

            m["score"] = score
            if score >= 0.6:
                best_matches.append(m)
                if score > best_score:
                    best_score = score

        # Deduplicate matches by source
        seen_sources = set()
        deduped = []
        for m in sorted(best_matches, key=lambda x: -x["score"]):
            if m["source"] not in seen_sources:
                deduped.append(m)
                seen_sources.add(m["source"])

        # Determine verdict
        if best_score >= 0.85:
            verdict, confidence = "VERIFIED", best_score
        elif best_score >= 0.65:
            verdict, confidence = "LIKELY_REAL", best_score
        elif best_score >= 0.4:
            verdict, confidence = "SUSPICIOUS", best_score
            notes.append("Partial matches found but confidence is low.")
        else:
            verdict, confidence = "NOT_FOUND", 0.0
            notes.append("No matches found in Crossref, Semantic Scholar, or OpenAlex.")

        return VerificationResult(
            citation=citation,
            verdict=verdict,
            confidence=confidence,
            matches=deduped,
            notes=notes,
        )

    def verify_batch(self, citations: list[dict]) -> list[VerificationResult]:
        return [self.verify(c) for c in citations]


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
"""
if __name__ == "__main__":
    verifier = CitationVerifier()

    test_citations = [
        {
            "title": "Attention is all you need",
            "authors": ["Vaswani", "Shazeer", "Parmar"],
            "year": 2017,
            "journal": "Advances in Neural Information Processing Systems",
        },
        {
            "title": "Deep learning for predicting stock market crashes using quantum neural networks",
            "authors": ["Smith", "Johnson"],
            "year": 2021,
            "journal": "Journal of Fictional Finance",
        },
    ]

    for citation in test_citations:
        print("\n" + "=" * 60)
        result = verifier.verify(citation)
        print(result)
"""
