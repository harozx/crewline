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


def test_shim_clis_get_multiline_prompt_on_stdin(monkeypatch):
    from crewline.crew import adapters
    from crewline.crew.adapters import _cmd
    monkeypatch.setattr(adapters, "_exe", lambda name: name)   # CI has no agent CLIs installed
    from crewline.crew.models import Choice
    for cli in ("claude", "codex"):
        argv, stdin = _cmd(Choice(cli, "m"), "line1\nline2", write=True, timeout=60)
        assert stdin == "line1\nline2" and "line2" not in " ".join(argv)


def test_quota_block_removes_cli_from_routing(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWLINE_DATA", str(tmp_path))
    monkeypatch.setenv("CREWLINE_CLIS", "agy,claude,codex")
    from crewline.crew.models import block_quota, pick
    block_quota("codex")
    assert all(c.cli != "codex" for c in pick("medium"))
    block_quota("claude", hours=-1)   # an expired block does not count
    assert any(c.cli == "claude" for c in pick("heavy"))


def test_only_enabled_clis_are_routed(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWLINE_DATA", str(tmp_path))
    monkeypatch.delenv("CREWLINE_CLIS", raising=False)
    from crewline.crew.models import pick
    for tier in ("light", "medium", "heavy"):
        assert {c.cli for c in pick(tier)} == {"agy"}
    # writer Claude-via-agy still gets a reviewer from another vendor
    assert all(c.vendor != "anthropic" for c in pick("heavy", avoid_vendor="anthropic"))


def test_test_file_detection_across_languages():
    for t in ("src/foo_test.go", "web/a.test.ts", "web/a.spec.tsx", "core/FooTest.java", "tests/x.py",
              "crates/img/tests/blur.rs", "app/__tests__/x.js", "test_util.py", "ui/docking_tests.rs"):
        assert is_test(t), t
    for c in ("src/latest.ts", "core/Contest.java", "crates/img/src/blur.rs", "pkg/attest/sign.go"):
        assert not is_test(c), c


def test_due_dates_drive_urgency():
    import datetime as dt

    from crewline.map.build import _urgency
    today = dt.date.today()
    overdue = {"due": (today - dt.timedelta(days=3)).isoformat()}
    soon = {"release_date": (today + dt.timedelta(days=5)).isoformat()}
    later = {"due": (today + dt.timedelta(days=60)).isoformat()}
    assert _urgency(overdue) == ("due date passed 3 days ago", 1.0)
    assert _urgency(soon) == ("release in 5 days", 0.8)
    assert _urgency(later)[1] < _urgency(soon)[1]
    assert _urgency({})[1] == 0.0


def test_parent_child_and_siblings_are_not_collisions():
    from crewline.map.build import mark_family, overlaps, rollup_parents

    def t(k, p):
        return {"key": k, "parent": p, "files": ["a.py"], "modules": ["m"], "impact": [], "priority_score": 1,
                "assignee": None, "status": "Open"}

    tickets = [t("E-1", None), t("E-2", "E-1"), t("E-3", "E-1"), t("X-9", None)]
    cols = overlaps(tickets)
    mark_family(cols, {x["key"]: x["parent"] for x in tickets})
    for x in tickets:
        x["overlaps"] = [c for c in cols if x["key"] in (c["a"], c["b"])]
    family = {frozenset((c["a"], c["b"])) for c in cols if c["same_parent"]}
    assert frozenset(("E-2", "E-3")) in family and frozenset(("E-1", "E-2")) in family
    assert frozenset(("E-2", "X-9")) not in family
    assert rollup_parents(tickets)[0]["collides_outside"] == ["X-9"]


def test_jira_and_git_names_match_the_same_person():
    # assignee fit compares Jira display names with git author names; a miss marks a ticket "new" wrongly
    from crewline.map.build import same_person
    assert same_person("Chang Chi Hsu", "Chang-Chi Hsu")
    assert same_person("Chia-Cheng Chueh", "Chia-Cheng Chueh  (add mul)")
    assert same_person("Muralidhar Basani", "Murali Basani")
    assert same_person("José García", "Jose Garcia")
    assert not same_person("David Jacot", "David Arthur")
    assert not same_person(None, "Alan Lau")
