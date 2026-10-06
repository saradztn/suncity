// Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
// sky.fx - procedural sky dome (the camera-following sphere model "skydome", drawn at the far plane).
//   * scattering-shaped sky: zenith / horizon gradient whose brightening follows the sun side (Mie forward scatter)
//   * real sun disc with limb darkening + halo, moon with a soft glow, star field at night
//     (the cloud deck was removed on purpose: its dark bases read as black rays / smudges
//      around the moon and the user asked to delete them - only the gCloud* uniforms remain,
//      the weather engine still drives them)
//   * two drifting cloud layers from PROCEDURAL value noise (computed in the shader - no texture to load,
//     bind or magnify): coverage from the weather, lit toward the sun with a silver lining, dark bases, storm
//     darkening, horizon fade into the haze band
//   * lightning flash (gFlash) lights the whole dome and the clouds
// The direction is the model-space position (the object sits on the camera and never rotates), the vertex shader pins
// the dome to the far plane so every drawn pixel is behind the whole scene.  Shader model 3.
// ---- Time / weather colours come from the env.lua timecycle (gSunDir, gSunColor, gZenith, gHorizon, ...): the shader
// ---- shapes them physically; the engine cannot re-light the baked city geometry any other way.
float4x4 gWorldViewProjection : WORLDVIEWPROJECTION;
float3 gCameraPosition : CAMERAPOSITION;
float gTime : TIME;

// ---- environment uniform block (shared by every NightCity shader, pushed by client.lua)
float3 gSunDir = float3(0.0, 0.0, 1.0);
float3 gSunColor = float3(1.0, 1.0, 1.0);
float gSunI = 0.0;
float3 gMoonDir = float3(0.0, 0.0, 1.0);
float3 gAmbient = float3(0.1, 0.11, 0.14);
float gNightKeep = 1.0;
float gNightGlow = 1.0;
float gNight = 1.0;
float3 gZenith = float3(0.02, 0.03, 0.08);
float3 gHorizon = float3(0.16, 0.12, 0.2);
float3 gFogColor = float3(0.12, 0.1, 0.16);
float2 gFogRange = float2(200.0, 900.0);
float gCloudCover = 0.8;
float gCloudDark = 0.5;
float2 gWind = float2(0.6, 0.2);
float gFlash = 0.0;
float gQuality = 2.0;
float gDim = 1.0;
float gWet = 1.0;
float gPuddle = 1.0;
float gExposure = 1.0;
// ---- sky extras
float gHaze = 0.5;
float gMie = 0.5;

struct VSInput
{
    float3 Position : POSITION0;
    float2 TexCoord : TEXCOORD0;
};

struct VSOutput
{
    float4 Position : POSITION0;
    float3 Dir : TEXCOORD0;
};

struct PSInput
{
    float3 Dir : TEXCOORD0;
};

VSOutput VertexShaderFunction(VSInput VS)
{
    VSOutput O;
    O.Dir = VS.Position;                                   // unit sphere: the direction from the camera
    float4 p = mul(float4(VS.Position * 2000.0, 1.0), gWorldViewProjection);
    p.z = p.w * 0.99995;                                   // pin to the far plane: always behind the scene
    O.Position = p;
    return O;
}

float hash21(float2 p)
{
    return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
}

// gradient (Perlin-style) noise: smooth rolling billows like the classic noise sheets, without the
// square-grid waviness of plain value noise and without any texture to load, bind or magnify
float2 grad2(float2 i)
{
    float a = hash21(i) * 6.2831853;
    return float2(cos(a), sin(a));
}

float pnoise(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    float2 u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);          // quintic fade
    float n = lerp(lerp(dot(grad2(i), f),
                        dot(grad2(i + float2(1.0, 0.0)), f - float2(1.0, 0.0)), u.x),
                   lerp(dot(grad2(i + float2(0.0, 1.0)), f - float2(0.0, 1.0)),
                        dot(grad2(i + float2(1.0, 1.0)), f - float2(1.0, 1.0)), u.x), u.y);
    return 0.5 + 0.72 * n;
}

float2 rot45(float2 p)
{
    return float2(p.x * 0.7071 + p.y * 0.7071, p.y * 0.7071 - p.x * 0.7071);
}

// fbm: broad billows, medium structure, fine detail - each octave on a rotated domain so the
// octaves never beat into a visible grid pattern
float fbm3(float2 p)
{
    float f = pnoise(p * 0.32) * 0.58;
    f += pnoise(rot45(p) * 0.63 + 11.7) * 0.27;
    f += pnoise(p * 1.21 + 23.1) * 0.15;
    return f;
}

float fbm4(float2 p)
{
    float f = fbm3(p);
    if (gQuality >= 2.5)
    {
        f += pnoise(rot45(p) * 2.4 + 5.9) * 0.09;
    }
    return f;
}

// one cloud layer: world-anchored plane at height h (metres above the camera), noise cell size cs
float cloudLayer(float3 dir, float h, float cs, float cover, float seed)
{
    if (dir.z <= 0.015)
    {
        return 0.0;
    }
    // h / dir.z explodes at grazing angles and smears the noise domain into long radial STREAKS
    // across the sky (the old "lines in the sky").  The +0.28 keeps the projection nearly
    // isotropic (bounded ~3.6x stretch), and the most-stretched horizon band fades into the haze.
    float2 wp = gCameraPosition.xz + dir.xz * (h / (dir.z + 0.28));
    float2 p = (wp + gTime * gWind) / cs + seed;
    float n = fbm4(p);
    float lo = 0.62 - 0.42 * cover;
    float hi = lo + 0.30;
    float cov = smoothstep(lo, hi, n);
    return cov * smoothstep(0.03, 0.26, dir.z);
}

float4 PixelShaderFunction(PSInput PS) : COLOR0
{
    float3 dir = normalize(PS.Dir);
    float mu = dot(dir, gSunDir);
    float mu2 = saturate(mu * 0.5 + 0.5);

    // ---- scattering-shaped gradient: bright toward the sun, deeper opposite, haze band at the horizon
    float up = saturate(dir.z * 0.5 + 0.5);
    float3 col = lerp(gHorizon, gZenith, pow(up, 0.55));
    col += gSunColor * (gSunI * 0.22 + 0.04) * pow(mu2, 3.0) * gMie * (0.35 + 0.65 * up);
    float horizonBand = pow(1.0 - saturate(abs(dir.z)), 9.0);
    col = lerp(col, gFogColor, horizonBand * gHaze);

    // ---- sun disc + halo
    float sunAng = acos(clamp(mu, -1.0, 1.0));
    float disc = smoothstep(0.021, 0.014, sunAng);
    float limb = pow(saturate(1.0 - sunAng / 0.021), 0.35);
    col += gSunColor * gSunI * disc * limb * 2.4;
    col += gSunColor * gSunI * pow(saturate(mu), 42.0) * 0.55 * gMie;
    col += gSunColor * gSunI * pow(saturate(mu), 7.0) * 0.14 * gMie;

    // ---- moon + stars (night)
    float night = gNight * (1.0 - saturate(gSunI * 1.6));
    if (night > 0.01)
    {
        float mmu = dot(dir, gMoonDir);
        float mAng = acos(clamp(mmu, -1.0, 1.0));
        float mdisc = smoothstep(0.017, 0.012, mAng);
        float shade = 0.55 + 0.45 * pow(saturate(mmu * 0.5 + 0.5), 0.7);
        col += float3(0.86, 0.9, 1.0) * mdisc * shade * 1.15 * night;
        col += float3(0.5, 0.6, 0.82) * pow(saturate(mmu), 20.0) * 0.10 * night;
        float2 su = float2(atan2(dir.y, dir.x) * 3.8197, asin(clamp(dir.z, -1.0, 1.0)) * 3.8197);
        float2 sg = su * 30.0;
        float2 g = floor(sg);
        float2 f = frac(sg) - 0.5;                                    // a small round point inside each lit cell,
        float h = hash21(g);                                           // never the whole cell (that reads as a white square)
        float star = smoothstep(0.991, 1.0, h) * smoothstep(0.16, 0.015, dot(f, f));
        float tw = 0.55 + 0.45 * sin(gTime * (1.2 + h * 2.4) + h * 31.0);
        col += float3(0.85, 0.9, 1.0) * (star * tw * 1.7 * night * smoothstep(0.02, 0.25, dir.z));
    }

    // ---- clouds: DELETED (see the header) - the dark deck was the "black rays" around the moon.
    //      The gCloud* uniforms stay declared so the weather engine (and its tests) keep working.

    // ---- below the horizon: the haze the distant geometry fades into
    col = lerp(col, gFogColor, smoothstep(0.0, -0.16, dir.z));

    // ---- lightning lights the sky
    col += gFlash * 0.30 * float3(0.82, 0.86, 1.0) * (0.45 + 0.55 * up);

    return float4(saturate(col * gDim), 1.0);
}

technique tec0
{
    pass P0
    {
        VertexShader = compile vs_3_0 VertexShaderFunction();
        PixelShader = compile ps_3_0 PixelShaderFunction();
    }
}

technique fallback
{
    pass P0
    {
    }
}
