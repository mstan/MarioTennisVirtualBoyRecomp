// Optional developer capture of uncatalogued artwork. Never packaged game art.
#pragma once
#if defined(VBRECOMP_DEBUG_TOOLS)
#include <filesystem>
#include <sstream>
#include <unordered_set>
#include <vector>

namespace tennis {
inline void capture_missing(const VbRenderFrame* frame, const Materials& catalog,
                            const uint8_t* ids) {
    struct State {
        const char* destination=std::getenv("VB_TENNIS_CAPTURE_MISSING");
        bool failed=false;
        unsigned saved=0,frames=0,unknown_frames=0;
        uint32_t previous[2]={UINT32_MAX,UINT32_MAX};
        std::unordered_set<uint64_t> observed;
        ~State() {
            if(!destination || !*destination)return;
            const std::filesystem::path folder(destination);
            if(!folder.is_absolute())return;
            std::ofstream out(folder/"capture-summary.json",std::ios::binary);
            out<<"{\"eye_frames\":"<<frames<<",\"unknown_eye_frames\":"<<unknown_frames
               <<",\"saved_poses\":"<<saved<<",\"failed\":"<<(failed?"true":"false")
               <<",\"limit_reached\":"<<(saved>=1024?"true":"false")<<"}\n";
        }
    };
    static State state;
    const auto destination=state.destination;
    auto& failed=state.failed;auto& saved=state.saved;auto& observed=state.observed;
    if(!destination || !*destination || failed || saved>=1024)return;
    const std::filesystem::path folder(destination);
    if(!folder.is_absolute()) {failed=true;return;}
    const bool fresh=state.previous[frame->eye]!=frame->frame_seq;
    if(fresh) {++state.frames;state.previous[frame->eye]=frame->frame_seq;}
    bool unknown=false;
    struct Tile {uint32_t hash=0;uint16_t index=0;bool present=false,hflip=false,vflip=false;};
    struct Pose {
        std::array<uint8_t,128*128> pixels{};
        std::array<Tile,256> tiles{};
        std::vector<uint64_t> missing;
    };
    std::array<Pose,4> poses;
    for(unsigned i=0;i<VB_RENDER_PIXELS;++i) {
        const auto& s=frame->sources[i];
        if(!s.world || s.map!=0 || s.x>=512 || s.y<384 || s.y>=512)continue;
        const unsigned slot=s.x/128,c=ids[slot*2];
        if(c>6)continue;
        const unsigned x=s.x%128,y=s.y-384,tx=x/8,ty=y/8;
        auto& pose=poses[slot];
        pose.pixels[y*128+x]=s.raw;
        pose.tiles[ty*16+tx]={s.tile_hash,s.tile,true,(x&7)!=s.u,(y&7)!=s.v};
        const auto key=Materials::key(c,tx,ty,s.tile_hash);
        auto it=catalog.tiles.find(key);
        if(it==catalog.tiles.end() || !it->second[s.v*8+s.u]) {
            unknown=true;
            const auto pixel_key=(key<<6)|(s.v*8+s.u);
            if(!observed.count(pixel_key))pose.missing.push_back(pixel_key);
        }
    }
    if(fresh && unknown)++state.unknown_frames;
    for(unsigned slot=0;slot<4;++slot) {
        auto& pose=poses[slot];
        if(pose.missing.empty())continue;
        // Recover hidden texels only if live CHR still matches the fingerprint
        // recorded when this displayed tile was drawn. Otherwise keep the
        // captured visible texels; a later pose can complete the annotation.
        for(unsigned i=0;i<256;++i) {
            const auto& t=pose.tiles[i];
            if(!t.present)continue;
            uint16_t rows[8];uint32_t hash=2166136261u;
            for(unsigned y=0;y<8;++y) {
                rows[y]=vb_read16(0x78000u+t.index*16u+y*2u);
                hash=(hash^uint8_t(rows[y]))*16777619u;
                hash=(hash^uint8_t(rows[y]>>8))*16777619u;
            }
            if(hash!=t.hash)continue;
            for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x)
                pose.pixels[(i/16*8+y)*128+i%16*8+x]=
                    (rows[y^(t.vflip?7:0)]>>(2*(x^(t.hflip?7:0))))&3;
        }
        uint64_t fingerprint=14695981039346656037ull;
        auto mix=[&](uint8_t b) {fingerprint=(fingerprint^b)*1099511628211ull;};
        for(auto b:pose.pixels)mix(b);
        for(const auto& t:pose.tiles) {
            for(unsigned b=0;b<4;++b)mix(uint8_t(t.hash>>(8*b)));
            mix(t.present);mix(t.hflip);mix(t.vflip);
        }
        std::ostringstream name;
        name<<"c"<<unsigned(ids[slot*2])<<"-128-live-"<<std::hex<<fingerprint<<".json";
        std::error_code error;
        std::filesystem::create_directories(folder,error);
        if(error) {failed=true;return;}
        const auto path=folder/name.str();
        if(!std::filesystem::exists(path,error)) {
            const auto temp=std::filesystem::path(path.string()+".tmp");
            std::ofstream out(temp,std::ios::binary);
            out<<"{\"character\":"<<unsigned(ids[slot*2])<<",\"size\":128,\"pixels\":[";
            for(unsigned i=0;i<pose.pixels.size();++i)out<<(i?",":"")<<unsigned(pose.pixels[i]);
            out<<"],\"tiles\":[";bool first=true;
            for(unsigned i=0;i<256;++i) {
                const auto& t=pose.tiles[i];if(!t.present)continue;
                out<<(first?"":",")<<"["<<i%16<<","<<i/16<<","<<t.hash<<","<<t.hflip<<","<<t.vflip<<"]";
                first=false;
            }
            out<<"]}\n";out.close();
            if(!out) {failed=true;return;}
            std::filesystem::rename(temp,path,error);
            if(error) {failed=true;return;}
            ++saved;
        }
        observed.insert(pose.missing.begin(),pose.missing.end());
    }
}
}
#else
namespace tennis {
inline void capture_missing(const VbRenderFrame*,const Materials&,const uint8_t*) {}
}
#endif
