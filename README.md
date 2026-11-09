# Flipper OS on Raspberry Pi

This is a port of Flipper OS for the RPI 4 family.

I tested it on a Pi 4 with a Waveshare DSI E screen. You can also select HDMI for using on a monitor. 

If your Pi is already running this port, put the `port` folder and the rebuilt ARM64 `flipctl` and `dtmerge` files in the same folder and then run:

```sh
sudo python3 port/install-runtime.py --ui ./flipctl --dtmerge ./dtmerge --preset waveshare-7-e --tint orange
```

For HDMI, replace `waveshare-7-e` with `hdmi`. (FlipperOS not raspbian)

If you'd rather have the white backlight ui:

```sh
sudo flipper-display configure --tint grayscale
sudo systemctl restart flipctl-display.service
```

Default login for SSH is `user` / `user`