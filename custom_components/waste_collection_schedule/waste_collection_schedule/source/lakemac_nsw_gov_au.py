from waste_collection_schedule import Collection, Icons  # type: ignore[attr-defined]
from waste_collection_schedule.service.OpenCities import (
    OpenCitiesClient,
    OpenCitiesConfig,
)

TITLE = "Lake Macquarie City Council"
DESCRIPTION = "Source for Lake Macquarie City Council, Australia."
URL = "https://www.lakemac.com.au/"
TEST_CASES = {
    "TestcaseI": {"address": "11 The Circlet, RATHMINES NSW 2283"},
    "TestcaseII": {"address": "386 Pacific Highway, MURRAYS BEACH NSW 2281"},
}

ICON_MAP = {
    "General waste": Icons.GENERAL_WASTE,
    "Recycling": Icons.RECYCLING,
    "Green waste": Icons.GARDEN,
    "Bulk waste": Icons.GENERAL_WASTE,
}

HEADERS = {
    "referer": "https://www.lakemac.com.au/For-residents/Waste-and-recycling/When-are-your-bins-collected"
}

_CONFIG = OpenCitiesConfig(
    domain="https://www.lakemac.com.au",
    headers=HEADERS,
    icon_keywords=ICON_MAP,
    # This deployment's search answers an unrelated query with one
    # confident-looking hit ("2 Wallarah Rd" -> "2 Lake Ridge Lane, MURRAYS
    # BEACH"), so require a real address match -- including when there is only
    # one result -- and offer the hits as suggestions otherwise.
    strict_address_matching=True,
    strict_single_result=True,
)


class Source:
    def __init__(self, address: str):
        self._address = address
        self._client = OpenCitiesClient(_CONFIG)

    def fetch(self) -> list[Collection]:
        return self._client.fetch(address=self._address)
