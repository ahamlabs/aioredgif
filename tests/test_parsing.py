from pathlib import Path

from aioredgif.parsing import (
    active_watch_id,
    classify_url,
    creator_from_html,
    ids_from_creator_html,
    ids_from_feed_html,
    posters_from_html,
)

FX = Path(__file__).parent / "fixtures"
NICHE = (FX / "niche_page.html").read_text()
CREATOR = (FX / "creator_page.html").read_text()
WATCH = (FX / "watch_page.html").read_text()


def test_creator_page_ids():
    ids = ids_from_creator_html(CREATOR)
    assert len(ids) == 8
    assert ids[0] == "mysteriousspottedzethusspinipes"
    assert "clearamazingdeviltasmanian" in ids


def test_creator_username_is_handle_not_display_name():
    assert creator_from_html(CREATOR) == "paul57ak57"
    assert creator_from_html(WATCH) == "paul57ak57"


def test_watch_page():
    assert active_watch_id(WATCH) == "mysteriousspottedzethusspinipes"
    feed = ids_from_feed_html(WATCH)
    assert feed[0] == "mysteriousspottedzethusspinipes"
    assert not any(i.startswith("feed-module") for i in feed)  # ads skipped


def test_posters():
    p = posters_from_html(CREATOR)
    assert p["mysteriousspottedzethusspinipes"].endswith("MysteriousSpottedZethusspinipes-mobile.jpg")


def test_classify():
    assert classify_url("https://www.redgifs.com/watch/mysteriousspottedzethusspinipes") == (
        "watch",
        "mysteriousspottedzethusspinipes",
    )
    assert classify_url("https://www.redgifs.com/users/paul57ak57") == ("creator", "paul57ak57")
    assert classify_url("https://www.redgifs.com/gifs/blonde") == ("tag", "blonde")
    assert classify_url("https://media.redgifs.com/SilentVisibleTarsier-mobile.jpg") == (
        "watch",
        "silentvisibletarsier",
    )
    assert classify_url("https://example.com/x")[0] == "unknown"


def test_niche_url_and_page():
    assert classify_url("https://www.redgifs.com/niches/lost-bet-captions") == ("niche", "lost-bet-captions")
    ids = ids_from_feed_html(NICHE)
    assert ids[0] == "querulousviolentgoose"
    assert len(ids) == 30
    assert not any(i.startswith("feed-module") for i in ids)
