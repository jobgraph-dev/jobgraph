# Any copyright is dedicated to the public domain.
# http://creativecommons.org/publicdomain/zero/1.0/

import pytest

import jobgraph
from jobgraph.main import main as jobgraph_main


@pytest.fixture
def run_main(maketgg, monkeypatch):
    def inner(args, **kwargs):
        kwargs.setdefault("target_jobs", ["_fake-t-0", "_fake-t-1"])
        tgg = maketgg(**kwargs)

        def fake_get_jobgraph_generator(*args):
            return tgg

        monkeypatch.setattr(
            jobgraph.main, "get_jobgraph_generator", fake_get_jobgraph_generator
        )
        jobgraph_main(args)
        return tgg

    return inner


@pytest.mark.parametrize(
    "attr,expected",
    (
        ("jobs", ["_fake-t-0", "_fake-t-1", "_fake-t-2"]),
        ("full", ["_fake-t-0", "_fake-t-1", "_fake-t-2"]),
        ("target", ["_fake-t-0", "_fake-t-1"]),
        ("target-graph", ["_fake-t-0", "_fake-t-1"]),
        ("optimized", ["_fake-t-0", "_fake-t-1"]),
    ),
)
def test_show_jobgraph(run_main, capsys, attr, expected):
    run_main([attr])
    out, err = capsys.readouterr()
    assert out.strip() == "\n".join(expected)
    assert "Dumping result" in err


def test_jobs_regex(run_main, capsys):
    run_main(["full", "--jobs=_.*-t-1"])
    out, _ = capsys.readouterr()
    assert out.strip() == "_fake-t-1"


def test_output_file(run_main, tmpdir):
    output_file = tmpdir.join("out.txt")
    assert not output_file.check()

    run_main(["full", f"--output-file={output_file.strpath}"])
    assert output_file.check()
    assert output_file.read_text("utf-8").strip() == "\n".join(
        ["_fake-t-0", "_fake-t-1", "_fake-t-2"]
    )
