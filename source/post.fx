// Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
// post.fx - cinematic grade for NightCity (switched with /ncfx).  Two techniques:
//   tec0 (ps_3_0): chromatic aberration, micro sharpen, bloom, volumetric-STYLE sun rays (screen-space radial
//         scattering toward the sun's screen position - an approximation, not true volumetrics), grade, lightning
//         exposure flash, vignette, film grain
//   tec1 (ps_2_0): the same grade without the rays (11 texture reads) for older cards
// Exposure (/ncexposure * gExposure from the timecycle), grain / rays fade with the quality preset (gQuality).
texture ScreenTexture;
float2 gPix = float2(0.0007, 0.0013);
float gTime = 0;
float gGain = 1.0;

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
// ---- post extras
float2 gSunScreen = float2(0.5, 0.5);
float gRayStrength = 0.0;

sampler S0 = sampler_state
{
    Texture = (ScreenTexture);
    MinFilter = Linear;
    MagFilter = Linear;
    AddressU = Clamp;
    AddressV = Clamp;
};

float3 gradeColor(float3 c, float2 uv)
{
    float2 o = gPix * 1.5;
    float3 n = tex2D(S0, uv + o).rgb + tex2D(S0, uv - o).rgb
             + tex2D(S0, uv + float2(o.x, -o.y)).rgb + tex2D(S0, uv + float2(-o.x, o.y)).rgb;
    n *= 0.25;
    c += (c - n) * 0.45;
    float2 w = gPix * 9.0;
    float3 b = tex2D(S0, uv + float2(w.x, 0.0)).rgb + tex2D(S0, uv - float2(w.x, 0.0)).rgb
             + tex2D(S0, uv + float2(0.0, w.y)).rgb + tex2D(S0, uv - float2(0.0, w.y)).rgb;
    b *= 0.25;
    c += max(b - 0.36, 0.0) * 0.95;
    float l = dot(c, float3(0.299, 0.587, 0.114));
    c = lerp(float3(l, l, l), c, 1.18);
    c = lerp(c, c * c * (3.0 - 2.0 * c), 0.45);
    c *= lerp(float3(0.86, 1.0, 1.12), float3(1.10, 0.98, 1.04), saturate(l * 1.6));
    return c;
}

float3 sunRays(float2 uv)
{
    float2 d = gSunScreen - uv;
    float2 p = uv;
    float2 st = d * 0.115;
    float3 acc = float3(0.0, 0.0, 0.0);
    float w = 1.0;
    for (int i = 0; i < 8; i++)
    {
        p += st;
        float3 s = tex2D(S0, p).rgb;
        acc += max(s - 0.42, 0.0) * w;
        w *= 0.86;
    }
    return acc * 0.22;
}

float4 PixelShaderFull(float2 uv : TEXCOORD0) : COLOR0
{
    float2 d0 = uv - 0.5;
    float r2 = dot(d0, d0);
    float2 ca = d0 * r2 * 0.014;
    float3 c;
    c.r = tex2D(S0, uv + ca).r;
    c.g = tex2D(S0, uv).g;
    c.b = tex2D(S0, uv - ca).b;
    c = gradeColor(c, uv);
    c += sunRays(uv) * gSunColor * (gRayStrength * (0.22 + 0.78 * saturate(gSunI * 1.4)));
    c *= gGain * gExposure * (1.0 + gFlash * 0.28);
    c *= saturate(1.0 - r2 * 1.25);
    float g = frac(sin(dot(uv * float2(913.0, 541.0) + gTime, float2(12.9898, 78.233))) * 43758.5453) - 0.5;
    if (gQuality >= 1.5)
    {
        c += g * 0.022;
    }
    return float4(saturate(c), 1.0);
}

float4 PixelShaderLite(float2 uv : TEXCOORD0) : COLOR0
{
    float2 d0 = uv - 0.5;
    float r2 = dot(d0, d0);
    float2 ca = d0 * r2 * 0.014;
    float3 c;
    c.r = tex2D(S0, uv + ca).r;
    c.g = tex2D(S0, uv).g;
    c.b = tex2D(S0, uv - ca).b;
    c = gradeColor(c, uv);
    c *= gGain * gExposure * (1.0 + gFlash * 0.28);
    c *= saturate(1.0 - r2 * 1.25);
    float g = frac(sin(dot(uv * float2(913.0, 541.0) + gTime, float2(12.9898, 78.233))) * 43758.5453) - 0.5;
    if (gQuality >= 1.5)
    {
        c += g * 0.022;
    }
    return float4(saturate(c), 1.0);
}

technique tec0
{
    pass P0
    {
        PixelShader = compile ps_3_0 PixelShaderFull();
    }
}

technique tec1
{
    pass P0
    {
        PixelShader = compile ps_2_0 PixelShaderLite();
    }
}

technique fallback
{
    pass P0
    {
    }
}
