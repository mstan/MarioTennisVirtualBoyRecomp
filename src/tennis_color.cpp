// Experimental presentation-only renderer. No writes to ROM, RAM or VIP state.
#include "renderer.h"
#include "mod_runtime.h"
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
unsigned player_color(int y, const Bounds& box, bool far) {
    if (far) return palette.opponent;
    const int t=100*(y-box.y0)/std::max(1,box.y1-box.y0+1);
    if (t<22) return palette.cap;
    if (t<42) return palette.skin;
    if (t<66) return palette.shirt;
    if (t<89) return palette.trousers;
    return palette.shoes;
}
void render(const VbRenderFrame* frame, uint32_t* out, void*) {
    std::array<Bounds,33> boxes{};
    std::array<int,224> left, right;
    std::array<int,384> skyline;
    left.fill(384); right.fill(-1); skyline.fill(96);
    for (int y=0;y<224;++y) for (int x=0;x<384;++x) {
        const int i=y*384+x, w=frame->worlds[i];
        if (w<1 || w>32) continue;
        auto& b=boxes[w]; ++b.count;
        b.x0=std::min(b.x0,x); b.x1=std::max(b.x1,x);
        b.y0=std::min(b.y0,y); b.y1=std::max(b.y1,y);
        if (w==29) { left[y]=std::min(left[y],x); right[y]=std::max(right[y],x); }
        if ((w==31 || w==32) && y<96) skyline[x]=std::min(skyline[x],y);
    }
    // World numbers are a game-specific heuristic, guarded against title/menu
    // reuse. VIP attribution is world+1, with zero denoting transparent pixels.
    // Service introduction and active rally shift the near player/net by one
    // world. Scenery uses separate left-only and right-only worlds (30/31).
    const int net=boxes[25].count>100 && boxes[25].y0>=110 ? 25 : 24;
    const int near=boxes[23].count>100 && boxes[23].y0>=110 ? 23 : 22;
    const bool match=boxes[29].count>300 && boxes[net].count>100
        && boxes[29].y0>=100 && boxes[net].y0>=110 && boxes[near].y0>=110;
    if (match) {
        // Interpolate missing scanlines between actual projected court edges.
        for(int y=boxes[29].y0;y<=boxes[29].y1;++y) if(right[y]<left[y]) {
            int a=y-1,b=y+1;
            while(a>=boxes[29].y0 && right[a]<left[a]) --a;
            while(b<=boxes[29].y1 && right[b]<left[b]) ++b;
            if(a>=boxes[29].y0 && b<=boxes[29].y1) {
                left[y]=(left[a]*(b-y)+left[b]*(y-a))/(b-a);
                right[y]=(right[a]*(b-y)+right[b]*(y-a))/(b-a);
            }
        }
        for(int y=boxes[29].y0+1;y<=boxes[29].y1;++y) {
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
            if(y>=boxes[29].y0 && y<=boxes[29].y1 && x>=left[y] && x<=right[y]) {
                color=palette.court; brightness=90;
            }
            const auto& score=boxes[28];
            if(score.count>100 && score.y1<100 && x>=score.x0 && x<=score.x1
                && y>=score.y0 && y<=score.y1) { color=0x16364c; brightness=100; }
            if(w) {
                brightness=shades[level];
                if(w==net) color=palette.net;
                else if(w==near) color=player_color(y,boxes[w],false);
                else switch(w-1) {
                case 30: case 31: color=palette.scenery; break;
                case 28:
                    color=level==3 ? palette.lines : palette.court;
                    brightness=level==3 ? 100 : 90;
                    break;
                case 26: color=player_color(y,boxes[w],true); break;
                case 25: color=0xe8ff71; brightness=100; break;
                default: color=0xffefb5; brightness=std::max(75,brightness); break;
                }
            }
        } else if(w || level) {
            // Menus remain native geometry and text, with a readable cool/warm
            // palette. Character-specific title/menu restoration is future work.
            static const unsigned ui[]={0xffcd67,0x71d8dc,0xf09565,0xc3a4ec};
            color=ui[(w+ y/48)%4]; brightness=shades[level];
        }
        if(!solid && !level) out[i]=frame->stock_argb[i];
        else out[i]=shade(color,brightness);
    }
}
void activate() {
    palette=Palette{}; solid=true; saturation=100;
    char value[1024];
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
        }
    }
    vb_renderer_register("marios-tennis.full-color",render,nullptr);
}
VB_MOD_CONSTRUCTOR(register_color) {
    vb_renderer_track_worlds();
    vb_mod_register_exclusive_plugin("marios-tennis.full-color","video.renderer",activate);
}
}
