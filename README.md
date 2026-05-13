# Stargazer

Stargazer is an autonomous location detection system that leverages sensor metrics from portable devices to determine observer position using stellar positioning relative to zenith in night sky photographs. The system analyzes star patterns in images to identify sky coordinates (via plate solving), then combines these coordinates with device sensor data (GPS, orientation, timestamp) to compute geographic location. Because the approach relies primarily on internal sensor inputs and periodic corrections from time-servers and astronomical catalogs - rather than continuous satellite or radio signals - it provides positioning capability in environments where conventional GNSS (GPS) or radio-based positioning is unavailable, degraded, or denied. This makes Stargazer particularly valuable for navigation in areas with poor satellite coverage, during signal disruptions, or in security - sensitive scenarios where external positioning signals may be unreliable.

## Requirements

- Android Studio 2021.1+
- Android SDK 35
- JDK 17+
- Gradle 8.5.2

## Installation

### From Source

```bash
# Clone repository
git clone https://github.com/yourusername/stargazer.git
cd stargazer/OpenCamera+/opencamera-code

# Build debug APK
./gradlew assembleDebug

# Install on connected device
./gradlew installDebug
```

## Project Structure

```
stargazer/
├── OpenCamera+/opencamera-code/
│   ├── app/src/main/
│   │   ├── java/net/sourceforge/opencamera/
│   │   │   ├── StargazerActivity.java
│   │   │   ├── MainActivity.java
│   │   │   ├── ImageSaver.java
│   │   │   └── ...
│   │   ├── python/
│   │   │   ├── main.py
│   │   │   ├── plate_solve.py
│   │   │   └── tools.py
│   │   ├── res/
│   │   │   ├── layout/activity_stargazer.xml
│   │   │   ├── drawable/ (button styles, icons)
│   │   │   └── values/ (strings, colors, styles)
│   │   └── AndroidManifest.xml
│   ├── build.gradle
│   └── settings.gradle
└── README.md
```

## About

**Author** - Vladyslav Mykhailov

- [astrometry.net](http://astrometry.net/) - Plate solving engine
- [astropy](https://www.astropy.org/) - Astronomical computations
- [OpenCamera](https://opencamera.sourceforge.io/) - Camera framework base

GPL-3.0. See LICENSE file for details.