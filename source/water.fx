// Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
// water.fx - the river surface (applied to the GTA water texture "waterclear256" with /ncfx 2).
//   * animated wave normals from procedural noise (two octaves + rain agitation while gWet is high)
//   * sky reflection approximation (zenith / horizon by the reflected ray, Fresnel) - NOT a real planar
//     reflection: DX9 / MTA expose no scene reflection texture for the water, so this mirrors the analytic
//     sky colours the dome shader draws, plus a strong sun glint
//   * deep colour from the timecycle (gWaterColor), distance haze, lightning flash
float4x4 gWorld : WORLD;
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
// ---- water extras
float3 gWaterColor = float3(0.04, 0.10, 0.13);

texture gTexture0 < string textureState = "0,Texture"; >;

sampler Sampler0 = sampler_state
{
    Texture = (gTexture0);
    MinFilter = Linear;
    MagFilter = Linear;
    MipFilter = Linear;
    AddressU = Wrap;
    AddressV = Wrap;
};

struct VSInput
{
    float3 Position : POSITION0;
    float3 Normal : NORMAL0;
    float2 TexCoord : TEXCOORD0;
};

struct VSOutput
{
    float4 Position : POSITION0;
    float2 TexCoord : TEXCOORD0;
    float3 WorldPos : TEXCOORD1;
    float3 WorldNormal : TEXCOORD2;
};

struct PSInput
{
    float2 TexCoord : TEXCOORD0;
    float3 WorldPos : TEXCOORD1;
    float3 WorldNormal : TEXCOORD2;
};

VSOutput VertexShaderFunction(VSInput VS)
{
    VSOutput O = (VSOutput)0;
    O.Position = mul(float4(VS.Position, 1.0), gWorldViewProjection);
    O.WorldPos = mul(float4(VS.Position, 1.0), gWorld).xyz;
    O.WorldNormal = mul(VS.Normal, (float3x3)gWorld);
    O.TexCoord = VS.TexCoord;
    return O;
}

float hash21(float2 p)
{
    return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453);
}

float vnoise(float2 p)
{
    float2 i = floor(p);
    float2 f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + float2(1.0, 0.0));
    float c = hash21(i + float2(0.0, 1.0));
    float d = hash21(i + float2(1.0, 1.0));
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

// slope of the animated wave field + rain rings while it rains
float2 waveSlope(float2 p, float t)
{
    float2 s = float2(vnoise(p * 0.9 + float2(t * 0.23, t * 0.11)) - 0.5,
                      vnoise(p * 0.9 + float2(-t * 0.17, t * 0.29) + 5.7) - 0.5);
    s += float2(vnoise(p * 2.6 + float2(t * 0.51, -t * 0.33)) - 0.5,
                vnoise(p * 2.6 + float2(t * 0.41, t * 0.47) + 9.1) - 0.5) * 0.55;
    float2 q = p * 1.4;
    float2 g = floor(q);
    float2 f = frac(q) - 0.5;
    float age = frac(t * 0.7 + hash21(g));
    float r = length(f);
    float k = (r - age * 0.5) * 24.0;
    float ring = exp(-k * k) * (1.0 - age);
    s += (f / max(r, 0.001)) * ring * 0.8 * gWet;
    return s;
}

float4 PixelShaderFunction(PSInput PS) : COLOR0
{
    float3 N = normalize(PS.WorldNormal);
    float3 V = normalize(PS.WorldPos - gCameraPosition);
    float2 slope = waveSlope(PS.WorldPos.xy * 0.22, gTime) * (0.12 + 0.10 * gWet);
    float3 Nw = normalize(float3(N.x + slope.x, N.y + slope.y, max(N.z, 0.2)));

    float ndv = saturate(dot(-V, Nw));
    float fres = 0.02 + 0.98 * pow(1.0 - ndv, 5.0);
    float3 R = reflect(V, Nw);

    // sky reflection approximation + sun glint
    float3 sky = lerp(gHorizon, gZenith, saturate(R.z * 1.35));
    sky *= 0.85 + 0.5 * saturate(dot(R, gSunDir)) * gSunI;
    float glint = pow(saturate(dot(R, gSunDir)), 180.0) * 5.5 + pow(saturate(dot(R, gSunDir)), 24.0) * 0.55;
    float3 col = lerp(gWaterColor * (0.55 + 0.45 * gDim), sky, saturate(fres * 1.25));
    col += gSunColor * glint * gSunI * (0.35 + 0.65 * fres);
    col += gAmbient * 0.35;

    // lightning + aerial perspective
    col += gFlash * 0.12;
    float dist = length(PS.WorldPos - gCameraPosition);
    float fogA = saturate((dist - gFogRange.x) / max(gFogRange.y - gFogRange.x, 1.0));
    col = lerp(col, gFogColor, fogA);
    return float4(saturate(col), 1.0);
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
