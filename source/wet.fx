// Created by: Arena.ai Agent Mode (AI) - NightCity MTA:SA resource
// wet.fx - the world surface shader of NightCity (applied per material class with /ncfx 2).  It EXTENDS the original
// rain-soaked ground shader - every old feature is kept - into a full time / weather surface model:
//   * dynamic lighting: baked night vertex light (dimmed by gNightKeep) + sky ambient + wrapped sun diffuse (gSunDir),
//     so the same city reads as dawn / noon / golden hour / night instead of a fixed midnight
//   * night emissive: bright texels (windows, neon, signs) glow with gNightGlow * gMatEmis, off during the day
//   * wetness: film + puddles from world-space noise (gWet / gPuddle, the env.lua drying model), rain rings in the
//     puddles (gMatRings), darkening per material class (gMatWet)
//   * reflections: screen-space reflection of the last captured frame (gScreen) with Fresnel + roughness blur (as before),
//     sky-coloured fallback reflection when the mirrored ray leaves the screen, sun glints (Blinn) on wet / glossy surfaces
//   * aerial perspective: distance haze toward the same fog colour the sky and GTA fog use
//   * the covered part of the river tunnel (gTun) stays dry
// One shader file, several dxCreateShader instances with different gMat* uniforms (ground / struct / metal / glass / neon).
// Shader model 3 (vs_3_0 / ps_3_0).  If the graphics card cannot run it MTA falls back to the empty technique.
float4x4 gWorld : WORLD;
float4x4 gWorldViewProjection : WORLDVIEWPROJECTION;
float4x4 gViewProjection : VIEWPROJECTION;
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
// ---- surface extras
float gReflect = 1.0;
float2 gPix = float2(0.0007, 0.0013);
float4 gTun = float4(0.0, 1.0, -1.0, 0.0);
float3 gVColFloor = float3(0.20, 0.22, 0.28);
float gMatWet = 1.0;
float gMatRefl = 1.0;
float gMatSpec = 1.0;
float gMatGloss = 40.0;
float gMatRings = 1.0;
float gMatEmis = 1.0;

texture gTexture0 < string textureState = "0,Texture"; >;
texture gScreen;

sampler Sampler0 = sampler_state
{
    Texture = (gTexture0);
    MinFilter = Anisotropic;
    MagFilter = Linear;
    MipFilter = Linear;
    MaxAnisotropy = 8;
};

sampler SamplerS = sampler_state
{
    Texture = (gScreen);
    MinFilter = Linear;
    MagFilter = Linear;
    MipFilter = None;
    AddressU = Clamp;
    AddressV = Clamp;
};

struct VSInput
{
    float3 Position : POSITION0;
    float3 Normal : NORMAL0;
    float4 Diffuse : COLOR0;
    float2 TexCoord : TEXCOORD0;
};

struct VSOutput
{
    float4 Position : POSITION0;
    float4 Diffuse : COLOR0;
    float2 TexCoord : TEXCOORD0;
    float3 WorldPos : TEXCOORD1;
    float3 WorldNormal : TEXCOORD2;
};

struct PSInput
{
    float4 Diffuse : COLOR0;
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
    O.Diffuse = VS.Diffuse;
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

// slope of the water surface: expanding rings around random drop points on a 1.3 m grid
float2 rainRings(float2 p, float t)
{
    float2 q = p * 0.77;
    float2 g = floor(q);
    float2 f = frac(q) - 0.5;
    float age = frac(t * 0.8 + hash21(g));
    float r = length(f);
    float k = (r - age * 0.45) * 28.0;
    float ring = exp(-k * k) * (1.0 - age);
    return (f / max(r, 0.001)) * ring;
}

float4 PixelShaderFunction(PSInput PS) : COLOR0
{
    float4 tex = tex2D(Sampler0, PS.TexCoord);
    // never darker than a soft floor: the vertex colour can be 0 for some objects once a world shader replaces the stock vertex stage
    float3 vcol = max(PS.Diffuse.rgb, gVColFloor);
    float3 N = normalize(PS.WorldNormal);

    // ---- dynamic lighting: baked night light (kept at night) + sky ambient + wrapped sun diffuse
    float ndl = dot(N, gSunDir);
    float3 sunD = gSunColor * (gSunI * 1.30 * saturate(ndl * 0.62 + 0.42));   // wrapped: daylight fills the facades
    float3 baseCol = tex.rgb * (vcol * gNightKeep + gAmbient + sunD);

    // ---- night emissive: windows / neon / signs (bright texels) glow after dark
    float lum = dot(tex.rgb, float3(0.299, 0.587, 0.114));
    float emis = smoothstep(0.5, 0.95, lum) * gNightGlow * gMatEmis;
    baseCol += tex.rgb * emis * 1.7;

    float up = saturate(N.z);
    float2 wxy = PS.WorldPos.xy;

    // ---- puddles (the deeper water dries last: gPuddle)
    float pn = vnoise(wxy * 0.045) * 0.60 + vnoise(wxy * 0.16 + 11.3) * 0.30 + vnoise(wxy * 0.70 + 3.1) * 0.10;
    float puddle = smoothstep(0.50, 0.64, pn) * up * saturate(0.25 + 0.75 * gPuddle);

    // ---- wetness: a film everywhere, deeper in the puddles, dry inside the tunnel
    float inTun = step(abs(PS.WorldPos.x - gTun.x), 9.0) * step(gTun.y, PS.WorldPos.y) * step(PS.WorldPos.y, gTun.z) * step(PS.WorldPos.z, gTun.w);
    float wet = saturate(gWet * (0.55 + 0.45 * puddle)) * lerp(0.35, 1.0, up) * (1.0 - 0.9 * inTun);

    baseCol *= lerp(1.0, 0.60, wet * gMatWet);

    // ---- surface normal with rain rings in the puddles
    float ringsOn = gMatRings * step(1.5, gQuality);
    float2 slope = rainRings(wxy, gTime) * puddle * 0.5 * ringsOn;
    float3 Nw = normalize(float3(N.x + slope.x, N.y + slope.y, max(N.z, 0.2)));

    // ---- sun glint (Blinn): the low sun smears golden streaks over wet asphalt and glass
    float3 V = normalize(PS.WorldPos - gCameraPosition);
    float3 H = normalize(gSunDir - V);
    float ndh = saturate(dot(Nw, H));
    float spec = pow(ndh, gMatGloss) * gMatSpec;
    baseCol += gSunColor * (gSunI * spec * (0.12 + 1.35 * wet) * (0.25 + 0.75 * saturate(ndl)));

    // ---- mirror term (screen-space reflection with a sky fallback)
    float3 R = reflect(V, Nw);
    float3 refPoint = PS.WorldPos + R * 70.0;
    float4 cp = mul(float4(refPoint, 1.0), gViewProjection);
    float2 uv = cp.xy / max(cp.w, 0.001) * float2(0.5, -0.5) + 0.5;
    float2 edge = saturate(min(uv, 1.0 - uv) * 10.0);
    float vis = edge.x * edge.y * step(0.5, cp.w);
    float dist = length(PS.WorldPos - gCameraPosition);
    vis *= saturate(1.0 - dist / 190.0);

    float blur = lerp(16.0, 5.0, puddle);              // pixels: rough wet film vs. smooth puddle
    blur = lerp(blur * 1.7, blur, step(1.5, gQuality));
    float2 o = gPix * blur;
    float3 refl = tex2D(SamplerS, uv).rgb * 0.4
                + tex2D(SamplerS, uv + float2(o.x, 0.0)).rgb * 0.15
                + tex2D(SamplerS, uv - float2(o.x, 0.0)).rgb * 0.15
                + tex2D(SamplerS, uv + float2(0.0, o.y)).rgb * 0.15
                + tex2D(SamplerS, uv - float2(0.0, o.y)).rgb * 0.15;
    float3 skyRefl = lerp(gHorizon, gZenith, saturate(R.z * 1.35)) * (0.85 + 0.6 * gSunI * saturate(dot(R, gSunDir)));
    refl = lerp(skyRefl, refl, vis);

    float ndv = saturate(dot(-V, Nw));
    float fres = 0.04 + 0.96 * pow(1.0 - ndv, 5.0);
    float strength = wet * (0.22 + 1.25 * fres + 0.55 * puddle) * gReflect * gMatRefl;
    float3 col = baseCol + refl * strength;

    // ---- lightning lifts the wet mirror a little
    col += gFlash * 0.06 * (0.4 + 0.6 * tex.rgb);

    // ---- aerial perspective (matches the sky haze band and GTA fog)
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
