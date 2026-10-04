# WetStreets - rain wetness for the vanilla San Andreas map

A standalone companion of the **NightCity** resource: the same rain-wet street look — screen-space
reflections, puddles, rain ripples, sun glints, night emissive glow and the cinematic grade —
applied to the **stock GTA:SA roads and pavements**.  It never changes the vanilla sky, clock or
weather: it *follows* them (`getTime()`, `getWeather()`, `getRainLevel()`), and the streets soak
and dry with the rain like in NightCity.

## Install

1. Copy the `WetStreets` folder into your server's `resources/` directory
   (it is produced by `python3 source/build.py` as `resource/WetStreets/`).
2. In the server console: `start WetStreets` (or add `WetStreets` to your `mtaserver.conf`).
3. Done - when it rains (weather 8 / 16, or any `setRainLevel`), the streets get wet, puddles fill,
   the rain rings appear and the low sun smears golden streaks over the asphalt.

Requires a graphics card that can run shader model 3 (`ps_3_0`).  On weaker cards the resource
degrades gracefully (or runs plain).

## Commands

| command | what it does |
|---|---|
| `/wetfx [0\|1\|2]` | graphics mode: `0` plain, `1` cinematic grade only, `2` wet streets + grade. Without argument it cycles. |
| `/wetlevel <0 .. 1\|auto>` | force the street wetness (`auto` = driven by the weather again) |
| `/wetflash` | fire a lightning strike (bright in the wet reflections) |
| `/wetinfo` | status: clock / weather / wetness, and how many vanilla textures each group captured |

## What it covers

The shader is applied to the vanilla textures by name (wildcards, see `GROUPS` in `wetstreets.lua`):

* `road` - `*road* *tar* *hiway* *freeway* *cross*`
* `pavement` - `*pave* *sidewalk* *walk* *kerb* *curb* *step*`
* `concrete` - `*conc* *floor* *slab* *plaza* *deck*`
* `metal` - `*steel* *metal* *grate* *manhole* *bridge*`

Add your own patterns to the list (e.g. custom road packs) and restart the resource.  `/wetinfo`
tells you how many visible textures each pattern matches.

## Optional: thunder sound

Drop a `thunder.wav` into the `WetStreets` folder and lightning strikes will play it (delayed,
like real thunder).  Without the file the flash is silent.

## Weather mapping

The vanilla weather ids drive cloud cover / wetness / lightning (see `WX` in `env.lua`):
clear weathers stay dry, `8` (rainy SF) and `16` (rainy countryside) soak the streets and fire
lightning, fog and clouds in between.  The actual `getRainLevel()` always wins over the preset,
so any resource that drives the rain drives the wetness.
