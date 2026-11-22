from crewline.crew.models import pick
from crewline.locate.baseline import fuse, is_test
from crewline.locate.text import tokens


def test_reviewer_never_same_vendor_when_alternative_exists():
    for tier in ("light", "medium", "heavy"):
        for c in pick(tier, avoid_vendor="anthropic"):
            assert c.vendor != "anthropic"


def test_rate_limited_cli_is_skipped():
    assert all(c.cli != "agy" for c in pick("light", blocked={"agy"}))


def test_tokens_split_camel_case_and_paths():
    t = tokens("core/src/main/java/org/apache/kafka/ReplicaManager.java")
    assert {"replica", "manager", "replicamanager", "core"} <= set(t)


def test_fuse_rewards_agreement():
    assert fuse(["a", "b"], ["b", "c"])[0] == "b"


def test_test_files_excluded_from_gold():
    assert is_test("clients/src/test/java/FooTest.java")
    assert not is_test("clients/src/main/java/Foo.java")


def test_wiki_images_with_spaces_and_code_kept_verbatim():
    from crewline.reader.markup import wiki_to_md
    md = wiki_to_md("h2. Bug\n!Screenshot 2026 at 1.59 PM.png|width=300!\n{code:java}a*b*c{code}")
    assert "## Bug" in md
    assert "![image: Screenshot 2026 at 1.59 PM.png](attachment:Screenshot 2026 at 1.59 PM.png)" in md
    assert "```java\na*b*c\n```" in md
