// Created by: Arena.ai Agent Mode (AI) - MTA:SA asset pipelines (shared tool, also used by FishingRod / Castle)
// librw_check.cpp - loads one .dff and its .txd with the *reference* RenderWare
// implementation (aap/librw, same chunk readers GTA SA's RW 3.6 is modelled on) and dumps what it parsed.
// Build: see source/tools/build_librw_check.sh      Run on every model: python3 validate.py --librw
#include <rw.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace rw;

static int fails = 0;
#define CHECK(c, ...) do { if(!(c)) { printf("  FAIL: " __VA_ARGS__); printf("\n"); fails++; } } while(0)

int main(int argc, char **argv)
{
	if(argc < 3){ printf("usage: librw_check model.dff texture.txd\n"); return 2; }
	if(!Engine::init()) return 3;
	rw::registerMeshPlugin();
	rw::registerNativeDataPlugin();
	rw::registerAtomicRightsPlugin();
	rw::registerMaterialRightsPlugin();
	rw::registerSkinPlugin();
	rw::registerUserDataPlugin();
	rw::registerHAnimPlugin();
	rw::registerMatFXPlugin();
	rw::registerUVAnimPlugin();
	if(!Engine::open(nil)) return 4;
	if(!Engine::start()) return 5;

	// ---- TXD
	StreamFile in;
	if(!in.open(argv[2], "rb")){ printf("cannot open txd\n"); return 6; }
	if(!findChunk(&in, ID_TEXDICTIONARY, nil, nil)){ printf("TXD: no texture dictionary chunk\n"); return 7; }
	TexDictionary *txd = TexDictionary::streamRead(&in);
	in.close();
	if(txd == nil){ printf("TXD: streamRead failed\n"); return 8; }
	int ntex = 0;
	FORLIST(lnk, txd->textures){
		Texture *t = Texture::fromDict(lnk);
		Raster *r = t->raster;
		printf("  TXD tex %-16s %4dx%-4d depth %2d levels %2d format 0x%04x\n", t->name, r->width, r->height, r->depth, r->getNumLevels(), r->format);
		CHECK(r->width > 0 && r->height > 0, "bad raster size");
		ntex++;
	}
	printf("TXD OK: %d textures parsed by librw\n", ntex);

	TexDictionary::setCurrent(txd);   // like the game: textures of the DFF resolve against the TXD
	// ---- DFF
	StreamFile din;
	if(!din.open(argv[1], "rb")){ printf("cannot open dff\n"); return 9; }
	if(!findChunk(&din, ID_CLUMP, nil, nil)){ printf("DFF: no clump\n"); return 10; }
	Clump *clump = Clump::streamRead(&din);
	din.close();
	if(clump == nil){ printf("DFF: Clump::streamRead failed\n"); return 11; }
	int natom = 0, totv = 0, tott = 0;
	FORLIST(lnk, clump->atomics){
		Atomic *a = Atomic::fromClump(lnk);
		Geometry *g = a->geometry;
		Frame *f = a->getFrame();
		printf("  atomic %d: geometry verts %d tris %d materials %d flags 0x%x texCoordSets %d morph %d frame (%.4f %.4f %.4f)\n",
		       natom, g->numVertices, g->numTriangles, g->matList.numMaterials, g->flags, g->numTexCoordSets, g->numMorphTargets,
		       f->matrix.pos.x, f->matrix.pos.y, f->matrix.pos.z);
		CHECK(g->numTexCoordSets == 1, "texcoord sets");
		CHECK(g->flags & Geometry::NORMALS, "normals flag");
		CHECK(g->flags & Geometry::POSITIONS, "positions flag");
		CHECK(g->flags & Geometry::TEXTURED, "textured flag");
		for(int i = 0; i < g->numTriangles; i++){
			Triangle *t = &g->triangles[i];
			CHECK(t->v[0] < g->numVertices && t->v[1] < g->numVertices && t->v[2] < g->numVertices, "tri %d index out of range", i);
			CHECK(t->matId < g->matList.numMaterials, "tri %d material id %d out of range", i, t->matId);
			if(fails > 10) return 20;
		}
		MeshHeader *mh = g->meshHeader;
		CHECK(mh != nil, "no mesh header (BinMesh)");
		int sum = 0;
		if(mh){
			for(uint32 i = 0; i < mh->numMeshes; i++){
				Mesh *m = &mh->getMeshes()[i];
				sum += m->numIndices;
				int mi = -1; for(int q = 0; q < g->matList.numMaterials; q++) if(g->matList.materials[q] == m->material) mi = q;
				printf("     mesh %u: material %d indices %u\n", i, mi, m->numIndices);
				CHECK(m->material != nil, "mesh without material");
				for(uint32 k = 0; k < m->numIndices; k++) CHECK(m->indices[k] < g->numVertices, "mesh index range");
			}
			CHECK(sum == g->numTriangles * 3, "BinMesh index total %d != tris*3 %d", sum, g->numTriangles * 3);
		}
		for(int i = 0; i < g->matList.numMaterials; i++){
			Material *m = g->matList.materials[i];
			MatFX *fx = MatFX::get(m);
			printf("     mat %d: tex=%s rgba=%d,%d,%d,%d surf=(%.1f %.1f %.1f) matfx=%s\n", i, m->texture ? m->texture->name : "(none)",
			       m->color.red, m->color.green, m->color.blue, m->color.alpha, m->surfaceProps.ambient, m->surfaceProps.specular, m->surfaceProps.diffuse,
			       fx ? (fx->type == MatFX::ENVMAP ? "ENVMAP" : "other") : "none");
			CHECK(m->texture != nil, "material %d has no texture", i);
			if(fx && fx->type == MatFX::ENVMAP)
				printf("        env coef %.2f tex %s\n", fx->fx[0].env.coefficient, fx->fx[0].env.tex ? fx->fx[0].env.tex->name : "(null)");
		}
		totv += g->numVertices; tott += g->numTriangles;
		natom++;
	}
	printf("DFF OK: %d atomics, %d vertices, %d triangles parsed by librw\n", natom, totv, tott);
	printf(fails ? "RESULT: %d FAILURES\n" : "RESULT: ALL librw CHECKS PASSED\n", fails);
	return fails ? 1 : 0;
}
