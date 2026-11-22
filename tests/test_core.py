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


def test_memory_recall_respects_acl_and_date(tmp_path):
    from crewline.memory.store import Item, Memory
    m = Memory(tmp_path / "m.sqlite")
    m.add(Item("org/public", "a/B.java", "pitfall", "public lesson", "u1", "s1", "2026-01-01"))
    m.add(Item("org/secret", "a/B.java", "pitfall", "secret lesson", "u2", "s2", "2026-01-02"))
    m.add(Item("org/public", "a/C.java", "convention", "same dir", "u3", "s3", "2026-03-01"))
    got = m.recall(["a/B.java"], allowed=lambda scope: scope == "org/public")
    assert [i.lesson for i in got] == ["public lesson", "same dir"]
    assert [i.lesson for i in m.recall(["a/B.java"], lambda s: True, before="2026-01-02")] == ["public lesson"]
