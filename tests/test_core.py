import base64, pytest

from kittytgp import build_render_bytes, fit_grid, kitty_probe, kitty_supported, png_size, render_parts
from kittytgp.core import DIACRITICS, KITTY_PROBE_ID, PLACEHOLDER, _wrap_tmux_passthrough

PNG_1X1 = base64.b64decode(b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2pF6kAAAAASUVORK5CYII=")


def test_probe_and_render_png(tmp_path):
    probe = kitty_probe(passthrough='none')
    assert probe.startswith(b'\x1b_G') and probe.endswith(b'\x1b[c')
    assert kitty_supported(f'\x1b_Gi={KITTY_PROBE_ID};OK\x1b\\\x1b[?62c'.encode())
    assert not kitty_supported(b'\x1b[?62c')
    path = tmp_path/'dot.png'
    path.write_bytes(PNG_1X1)
    assert png_size(path) == png_size(PNG_1X1) == (1, 1)
    transmit, placeholder = render_parts(path, cols=3, rows=2, image_id=0x123456, passthrough='none')
    assert transmit.startswith(b'\x1b_G') and transmit.endswith(b'\x1b\\')
    control, encoded = transmit[3:-2].split(b';', 1)
    assert set(control.split(b',')) >= {b'a=T', b'f=100', b'q=2', b'U=1', b'i=1193046', b'c=3', b'r=2', b'm=0'}
    assert base64.b64decode(encoded) == PNG_1X1
    rows = placeholder.removeprefix('\x1b[38;2;18;52;86m').removesuffix('\x1b[39m').split('\n')
    assert rows == [PLACEHOLDER + DIACRITICS[r] + PLACEHOLDER*2 for r in range(2)]
    combined = build_render_bytes(PNG_1X1, cols=3, rows=2, image_id=0x123456, passthrough='none', newline=False)
    assert combined == transmit + placeholder.encode()
    wrapped = _wrap_tmux_passthrough(transmit)
    assert wrapped.startswith(b'\x1bPtmux;\x1b\x1b_G') and wrapped.endswith(b'\x1b\x1b\\\x1b\\')
    with pytest.raises(ValueError): render_parts(PNG_1X1, cols=3, rows=2, image_id=1 << 24, passthrough='none')


def test_fit_grid():
    assert fit_grid(10, 20, 40) == (10, 10)  # small image: one column per pixel, cells twice as tall
    assert fit_grid(400, 300, 40) == (40, 15)  # wide image: scaled to the column budget
    assert fit_grid(25, 25, 7) == (7, 4)  # 25 * (7/25) rounds just above 7, and the budget still holds
    assert fit_grid(100, 1000, 40, max_rows=10) == (2, 10)  # the row budget binds
    assert fit_grid(80, 160, 40, cell_width_px=8, cell_height_px=16) == (10, 10)  # real cells: true size
    assert fit_grid(1, 10_000, 40) == (1, len(DIACRITICS))  # the most rows placeholders can address
