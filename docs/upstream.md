# Upstream notes

This repository is a fork of the vendor's configuration for the Eyelash Sofle.
The original README was written in Chinese, with an English translation
alongside it; both are preserved here so nothing from upstream is lost, and so
the top-level `README.md` can be about *this* configuration instead.

## Vendor changelog

Dates and wording are the vendor's, translated. They describe firmware released
by the vendor, not changes made in this fork.

- **2025-03-30** — Idle sleep timeout raised to one hour. Debounce time
  increased. Power consumption after sleep improved.
- **2024-12-21** — ZMK Studio support added. Only the left half needs
  reflashing to use it.
- **2024-10-24** — Power supply mode changed to reduce power consumption. Fixed
  the automatic shut-off for the RGB power supply.

> The vendor notes: if your keyboard was last updated before 2024-10-24, update
> to the latest firmware.

## Contacting the vendor

For 3D-printable case files, or for a hardware fault with the keyboard itself,
the vendor asks that you email **380465425@qq.com**.

## Original text

The changelog above as it originally appeared:

```
# 更新列表
- 2025/3/30 增加睡眠进入时间1小时  增加防抖时间 优化睡眠后功耗
- 2024/12/21
  1. 增加zmk-studio支持（只需要刷新左手即可使用）。
- 2024/10/24
  1. 修改供电模式，功耗降低。
  2. 修正RGB供电自动关闭的功能。

> 如果您的键盘于10月24日之前更新，请更新最新的固件。

# 联系我

如需3D打印的模型文件或者键盘有任何异常和故障，请联系380465425@qq.com
```
