# kittytgp

`kittytgp` is a pure-Python package that renders images and animations in the terminal with kitty's graphics protocol using Unicode placeholders (`U+10EEEE`).

It offers high-performance rendering:

1. Transmit PNG data with kitty graphics protocol
2. Create a **virtual** placement with `U=1`
3. Print `U+10EEEE` placeholder text colored with the image ID

For GIF animations, `kittytgp` uses Kitty's advanced `a=T` command to substitute base frames dynamically, resulting in beautifully smooth terminal playbacks with zero scrolling side effects.

## Install

For basic PNG support (zero dependencies):
```bash
pip install kittytgp
```

For full multi-format (JPG, WebP, etc.) and GIF animation support:
```bash
pip install kittytgp[all]
```

## CLI

Render static images (PNG, JPG, etc.):
```bash
kittytgp image.jpg
kittytgp image.webp --cols 40 --rows 20
```

Play animations (GIF):
```bash
kittytgp animation.gif
kittytgp animation.gif --fps 24 --no-loop
```

Useful options:
```bash
kittytgp plot.png --cols 40
kittytgp plot.png --rows 20
kittytgp plot.png --cell-size 10x20
kittytgp plot.png --image-id 0x123456
kittytgp plot.png --no-newline
kittytgp animation.gif --fps 30
kittytgp animation.gif --no-loop
```

## Python API

```python
from kittytgp import render_image, play_animation

# Render any image
render_image("plot.png")
render_image("photo.jpg", cols=40)

# Play GIF animation
play_animation("loader.gif", fps=15, loop=True)
```

Or build the bytes yourself for manual transmission:

```python
from kittytgp import build_render_bytes

payload = build_render_bytes("plot.png")
```

## Design notes

This package is designed as a powerful terminal rendering engine:

- Pillow (`PIL`) is fully optional. If active, it seamlessly handles cross-format inputs.
- Unicode placeholders are used so images move and interact fluidly within terminals like `tmux`.
- 24-bit image IDs encoded in truecolor foreground color.
- tmux passthrough support out of the box.

By default it fits the image into the current terminal while preserving aspect ratio. If the terminal cannot report cell pixel size, pass `--cell-size`, `--cols`, or `--rows`.


