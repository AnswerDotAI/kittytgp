import base64

from kittytgp.core import (
    DIACRITICS,
    PLACEHOLDER,
    _parse_png_size,
    _placeholder_grid,
    _wrap_tmux_passthrough,
    build_render_bytes,
    normalize_image_id,
)

PNG_1X1 = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pF6kAAAAASUVORK5CYII="
)


def test_parse_png_size():
    assert _parse_png_size(PNG_1X1) == (1, 1)


def test_tmux_wrap_doubles_escapes():
    wrapped = _wrap_tmux_passthrough(b"\x1b_Gm=0;abc\x1b\\")
    assert wrapped.startswith(b"\x1bPtmux;")
    assert wrapped.endswith(b"\x1b\\")
    assert b"\x1b\x1b_G" in wrapped


def test_placeholder_grid_uses_row_inheritance_form():
    grid = _placeholder_grid(3, 2, 0x123456)
    assert grid.startswith("\x1b[38;2;18;52;86m")
    assert PLACEHOLDER in grid
    assert DIACRITICS[0] in grid
    assert DIACRITICS[1] in grid
    assert DIACRITICS[2] not in grid
    assert grid.count(PLACEHOLDER) == 6


def test_build_render_bytes_contains_protocol_and_placeholder():
    payload = build_render_bytes(
        PNG_1X1,
        cols=1,
        rows=1,
        image_id=0x123456,
        passthrough="none",
        newline=False,
    )
    assert payload.startswith(b"\x1b_Ga=T,f=100,q=2,U=1,i=1193046,c=1,r=1,m=0;")
    assert PLACEHOLDER.encode("utf-8") in payload
    assert payload.endswith(b"\x1b[39m")


def test_image_id_is_limited_to_24_bits():
    try:
        normalize_image_id(1 << 24)
    except ValueError as exc:
        assert "24 bits" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")

def test_render_parts_splits_transmit_and_placeholder():
    from kittytgp import render_parts, build_render_bytes
    transmit, placeholder = render_parts(PNG_1X1, cols=3, rows=2, image_id=7, passthrough="none")
    assert transmit.startswith(b"\x1b_G") and transmit.endswith(b"\x1b\\")
    assert PLACEHOLDER in placeholder and "\x1b_G" not in placeholder
    combined = build_render_bytes(PNG_1X1, cols=3, rows=2, image_id=7, newline=False, passthrough="none")
    assert combined == transmit + placeholder.encode()

def test_kitty_probe_and_supported():
    from kittytgp import kitty_probe, kitty_supported, kitty_env_hint
    from kittytgp.core import KITTY_PROBE_ID
    p = kitty_probe(passthrough="none")
    assert p.startswith(b"\x1b_G") and p.endswith(b"\x1b[c")  # query then the DA1 fence
    assert kitty_supported(f"\x1b_Gi={KITTY_PROBE_ID};OK\x1b\\\x1b[?62c".encode())
    assert not kitty_supported(b"\x1b[?62c")  # DA1 alone: fence reached, no graphics reply
    assert kitty_env_hint({"TERM": "xterm-kitty"})
    assert kitty_env_hint({"TERM_PROGRAM": "ghostty"})
    assert kitty_env_hint({"GHOSTTY_RESOURCES_DIR": "/Applications/Ghostty.app/x"})  # survives into tmux panes
    assert not kitty_env_hint({"TERM": "xterm-256color"})

def test_passthrough_warning(monkeypatch, capsys):
    import kittytgp.core as kc
    monkeypatch.setattr(kc, '_tmux_passthrough_enabled', lambda: False)
    monkeypatch.setattr(kc, '_warned_passthrough', False)
    monkeypatch.setenv('TMUX', '/tmp/fake,1,0')
    assert kc._resolve_passthrough('auto') == 'tmux'
    assert 'allow-passthrough' in capsys.readouterr().err
    kc._resolve_passthrough('tmux')
    assert capsys.readouterr().err == ''  # warned once only
    monkeypatch.setattr(kc, '_warned_passthrough', False)
    monkeypatch.setattr(kc, '_tmux_passthrough_enabled', lambda: True)
    kc._resolve_passthrough('tmux')
    assert capsys.readouterr().err == ''  # enabled: silent
