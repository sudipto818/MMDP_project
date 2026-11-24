# Real photos (not included)

The 34 original photos are not published. To re-run `score_real.py` / `analyze_real.py`, put your own JPEGs here:

```
data/real/
  screen_laptop_12cm/  A_1.jpg A_2.jpg B_1.jpg B_2.jpg    (A = parrots, B = house; 2 shots each)
  screen_laptop_20cm/  ...    screen_laptop_35cm/  ...    screen_laptop_50cm/  ...
  screen_phone_12cm/   ...    screen_phone_20cm/   ...    screen_phone_35cm/   ...
  direct_none/         ordinary photos of scenes (no screen)
  roi_overrides.csv    hand-placed picture regions for photos where auto-detection failed (included)
```

Camera: Motorola Edge 50 Fusion main camera, 4096x1842 JPEG, default settings. Screens: HP Victus 15 laptop (15.6", 1920x1080 LCD, 141 ppi) and Moto G32 (6.5", 1080x2400 LCD, about 405 ppi).
