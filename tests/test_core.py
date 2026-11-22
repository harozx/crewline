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
