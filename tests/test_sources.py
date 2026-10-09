import unittest
from unittest.mock import patch
from scholar_discovery import sources

class SourcesTests(unittest.TestCase):
    @patch("scholar_discovery.sources.fetch_json")
    def test_crossref_normalizes_public_metadata(self,fetch):
        fetch.return_value={"message":{"items":[
            {"DOI":"10.5555/ABC","title":["Example Work"],
             "published":{"date-parts":[[2025,5,17]]}},
            {"title":["No DOI"]}
        ]}}
        result=sources.crossref("example",10)
        self.assertEqual(result,[{"source_id":"10.5555/abc","doi":"10.5555/ABC","title":"Example Work","year":2025}])
        self.assertEqual(fetch.call_args[0][0],"https://api.crossref.org/works")

    @patch("scholar_discovery.sources.fetch_json")
    def test_openalex_adapter(self,fetch):
        fetch.return_value={"results":[
            {"id":"https://openalex.org/W1","doi":"https://doi.org/10.5555/abc",
             "title":"Example Work","publication_year":2025},
            {"id":"W2","title":None}
        ]}
        result=sources.openalex("example",3)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["source_id"],"https://openalex.org/W1")

    def test_bounds(self):
        with self.assertRaises(ValueError):sources.crossref("q",1000)
        with self.assertRaises(ValueError):sources.openalex("q",0)

if __name__=="__main__":unittest.main()
