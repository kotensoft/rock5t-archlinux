# Bootloader license material in images

For this ROCK5T image, install the exact Rockchip notice:

- Repository source: `LICENSES/Rockchip-DDR-LICENSE.TXT`
- Image destination: `/usr/share/licenses/rock5t-bootloader/Rockchip-DDR-LICENSE.TXT`
- Expected SHA256: `0b37e1522c36cf4579c45dfb138798c3cb5665fcf6302b95377179fbed38e35c`
- Upstream: `https://github.com/armbian/rkbin/blob/1d3c61008fa823936ae7a59615393f8294b64456/LICENSE.TXT`

Preserve this notice in the image and release documentation, alongside the
U-Boot/TF-A license and corresponding-source materials. The DDR component is
part of the board-specific boot stack. Its license is distinct from the source
repository's GPL license; do not present or distribute it as standalone generic
open-source firmware. The exact notice controls its redistribution terms.

The new-image assembler must verify the installed notice hash before publication.
The presence of this source-tree copy alone does not prove it is in an image.
