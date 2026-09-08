// Experimental presentation-only renderer. No writes to ROM, RAM or VIP state.
#include "renderer.h"
#include "mod_runtime.h"
#include "memory.h"
#include "tennis_materials.h"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <fstream>
#include <string>

namespace {
struct Palette {
    unsigned sky = 0x64bfea, grass = 0x36734d, court = 0x3484ad;
    unsigned scenery = 0x56a45e, lines = 0xf4f0d1, net = 0xf4efdf;
    unsigned cap = 0xe44338, skin = 0xf5ba79, shirt = 0xe44338;
    unsigned trousers = 0x3975dc, shoes = 0x744734, opponent = 0xa97a49;
} palette;
bool solid = true;
int saturation = 100;
tennis::Materials materials;
tennis::Materials hud_materials;
std::array<unsigned,20> material_overrides;
const unsigned material_rgb[]={
    0x132439,0x242432,0xe83e34,0xf6bd86,0x3267ca,0x824c30,0xf6f5e9,
    0xf6cd48,0x43aa55,0xf184b2,0xf7d56a,0xa12532,0x52bdd3,0x4c302a,
    0x243f59,0x182331,0x839eaf,0xefab35,0x27864a,0xe83e34};
struct Bounds { int x0=384, x1=-1, y0=224, y1=-1, count=0; };
unsigned shade(unsigned rgb, int brightness) {
    int r=(rgb>>16)&255, g=(rgb>>8)&255, b=rgb&255;
    const int gray=(r*54+g*183+b*19)/256;
    r=gray+(r-gray)*saturation/100;
    g=gray+(g-gray)*saturation/100;
    b=gray+(b-gray)*saturation/100;
    return 0xff000000u | (std::clamp(r*brightness/100,0,255)<<16)
         | (std::clamp(g*brightness/100,0,255)<<8) | std::clamp(b*brightness/100,0,255);
}
unsigned material_color(uint8_t code) {
    unsigned rgb=material_rgb[code&31];
    switch(code&31) {
    case 2:rgb=palette.cap;break;
    case 3:rgb=palette.skin;break;
    case 4:rgb=palette.trousers;break;
    case 5:rgb=palette.shoes;break;
    case 19:rgb=palette.shirt;break;
    }
    if(material_overrides[code&31]<=0xffffff)rgb=material_overrides[code&31];
    const int tones[]={100,76,53,115};
    return shade(rgb,tones[code>>5]);
}
bool court_texel(const VbSourceTexel& s) {
    return s.world && s.map==0 && s.kind==2 && s.x>=160 && s.x<352 && s.y<288;
}
bool actor_texel(const VbSourceTexel& s) {
    return s.world && s.map==0 && s.x<512 && s.y>=384 && s.y<512;
}
unsigned actor_color(const VbSourceTexel& s,const uint8_t* ids) {
    const unsigned slot=s.x/128,c=ids[slot*2];
    if(c>6)return material_color(1);
    auto it=materials.tiles.find(tennis::Materials::key(c,(s.x%128)/8,(s.y-384)/8,s.tile_hash));
    if(it!=materials.tiles.end() && it->second[s.v*8+s.u])return material_color(it->second[s.v*8+s.u]);
    // An uncatalogued pose keeps its character's identity and native ink.
    // Never reinterpret a moving world number as skin or another character.
    const uint8_t base[]={2,8,9,8,6,7,5};
    return material_color(s.raw==3 ? 1 : base[c] | (s.raw==2 ? 32 : 0));
}
void render(const VbRenderFrame* frame, uint32_t* out, void*) {
    if(!frame->sources)return;
    const auto* ids=vb_wram_data()+0x203a;
    std::array<Bounds,33> boxes{};
    Bounds court;
    std::array<int,224> left, right;
    std::array<int,384> skyline;
    left.fill(384); right.fill(-1); skyline.fill(96);
    for (int y=0;y<224;++y) for (int x=0;x<384;++x) {
        const int i=y*384+x, w=frame->worlds[i];
        if (w<1 || w>32) continue;
        auto& b=boxes[w]; ++b.count;
        b.x0=std::min(b.x0,x); b.x1=std::max(b.x1,x);
        b.y0=std::min(b.y0,y); b.y1=std::max(b.y1,y);
        const auto& s=frame->sources[i];
        if (court_texel(s)) {
            left[y]=std::min(left[y],x); right[y]=std::max(right[y],x);
            ++court.count;court.y0=std::min(court.y0,y);court.y1=std::max(court.y1,y);
        }
        if (s.map==1 && s.y>=352 && s.y<432 && y<96) skyline[x]=std::min(skyline[x],y);
    }
    const bool match=court.count>300 && court.y0>=96;
    if (match) {
        // Interpolate missing scanlines between actual projected court edges.
        for(int y=court.y0;y<=court.y1;++y) if(right[y]<left[y]) {
            int a=y-1,b=y+1;
            while(a>=court.y0 && right[a]<left[a]) --a;
            while(b<=court.y1 && right[b]<left[b]) ++b;
            if(a>=court.y0 && b<=court.y1) {
                left[y]=(left[a]*(b-y)+left[b]*(y-a))/(b-a);
                right[y]=(right[a]*(b-y)+right[b]*(y-a))/(b-a);
            }
        }
        for(int y=court.y0+1;y<=court.y1;++y) {
            left[y]=std::min(left[y],left[y-1]);
            right[y]=std::max(right[y],right[y-1]);
        }
    }
    const int shades[4]={45,58,80,100};
    for(int y=0;y<224;++y) for(int x=0;x<384;++x) {
        const int i=y*384+x,w=frame->worlds[i],level=frame->levels[i];
        unsigned color=0x121f3a; int brightness=100;
        if(match) {
            color=y<96 ? palette.sky : palette.grass;
            brightness=y<96 ? 83+y*17/96 : 87;
            if(y>=skyline[x] && y<96) { color=palette.scenery; brightness=65; }
            if(y>=court.y0 && y<=court.y1 && x>=left[y] && x<=right[y]) {
                color=palette.court; brightness=90;
            }
            const auto& score=boxes[28];
            if(score.count>100 && score.y1<100 && x>=score.x0 && x<=score.x1
                && y>=score.y0 && y<=score.y1) { color=0x16364c; brightness=100; }
            if(w) {
                const auto& s=frame->sources[i];
                if(actor_texel(s)) {out[i]=actor_color(s,ids);continue;}
                if(s.map==1 && s.kind==0 && s.x>=16 && s.x<112 && s.y<35) {
                    auto it=hud_materials.tiles.find(tennis::Materials::key(0,s.x/8,s.y/8,s.tile_hash));
                    if(it!=hud_materials.tiles.end() && it->second[s.v*8+s.u]) {
                        out[i]=material_color(it->second[s.v*8+s.u]);continue;
                    }
                }
                brightness=shades[level];
                if(s.map==1 && s.y>=96 && s.y<112) color=palette.net;
                else if(s.map==1 && s.y>=352 && s.y<432) color=palette.scenery;
                else if(court_texel(s)) {
                    color=level==3 ? palette.lines : palette.court;
                    brightness=level==3 ? 100 : 90;
                }
                else if(s.kind==3) {color=0xe8ff71;brightness=level==1 ? 65 : 100;}
                else {color=0xf4f1dc;brightness=std::max(75,brightness);}
            }
        } else if(w || level) {
            const auto& s=frame->sources[i];
            if(s.map==1 && s.kind==0 && s.y>=48 && s.y<80 && s.x<336 && s.x%48<32 && !materials.tiles.empty()) {
                const unsigned c=s.x/48,u=s.x%48,v=s.y-48;
                out[i]=material_color(materials.portraits[c*1024+v*32+u]);continue;
            }
            color=level==3 ? 0xf6dc8c : 0x86bad0; brightness=shades[level];
        }
        if(!solid && !level) out[i]=frame->stock_argb[i];
        else out[i]=shade(color,brightness);
    }
}
void activate() {
    palette=Palette{}; solid=true; saturation=100;
    materials=tennis::Materials{};
    hud_materials=tennis::Materials{};
    material_overrides.fill(0x1000000);
    char value[1024];
    if(vb_mod_asset("materials.bin",value,sizeof(value)))materials.load(value);
    if(vb_mod_asset("hud-materials.bin",value,sizeof(value)))hud_materials.load(value);
    if(vb_mod_option("solid_surfaces",value,sizeof(value))) solid=std::string(value)=="true";
    if(vb_mod_option("saturation",value,sizeof(value))) saturation=std::clamp(std::atoi(value),0,100);
    if(vb_mod_asset("palette.txt",value,sizeof(value))) {
        std::ifstream input(value); std::string key; unsigned color;
        while(input>>key>>std::hex>>color) {
            if(color>0xffffff) continue;
            struct Entry { const char* name; unsigned* value; } entries[]={
                {"sky",&palette.sky},{"grass",&palette.grass},{"court",&palette.court},
                {"scenery",&palette.scenery},{"lines",&palette.lines},{"net",&palette.net},
                {"cap",&palette.cap},{"skin",&palette.skin},{"shirt",&palette.shirt},
                {"trousers",&palette.trousers},{"shoes",&palette.shoes},{"opponent",&palette.opponent}};
            for(auto& entry:entries) if(key==entry.name) *entry.value=color;
            static const char* names[]={"background","ink","cap","skin","trousers","brown","white","yellow","green","pink","hair","mouth","cyan","dark_hair","navy","pupil","racket","gold","shell","shirt"};
            for(unsigned i=0;i<material_overrides.size();++i)
                if(key==std::string("material.")+names[i])material_overrides[i]=color;
        }
    }
    vb_renderer_register("marios-tennis.full-color",render,nullptr);
}
VB_MOD_CONSTRUCTOR(register_color) {
    vb_renderer_track_texels();
    vb_mod_register_exclusive_plugin("marios-tennis.full-color","video.renderer",activate);
}
}
