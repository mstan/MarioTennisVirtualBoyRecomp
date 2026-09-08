// Data-only material maps keyed by original CHR fingerprints and atlas position.
// No decoded ROM artwork is stored in this catalog.
#pragma once
#include <array>
#include <cstdint>
#include <fstream>
#include <unordered_map>

namespace tennis {
struct Materials {
    std::array<uint8_t,7*32*32> portraits{};
    std::unordered_map<uint64_t,std::array<uint8_t,64>> tiles;
    static uint64_t key(unsigned c,unsigned x,unsigned y,uint32_t hash) {
        return uint64_t(hash) | uint64_t(x&15)<<32 | uint64_t(y&15)<<36 | uint64_t(c)<<40;
    }
    bool load(const char* path) {
        std::ifstream in(path,std::ios::binary);
        char magic[8];in.read(magic,8);
        if(!in || std::string(magic,8)!="VBMAT002")return false;
        uint8_t bytes[4]{};in.read(reinterpret_cast<char*>(bytes),4);
        if(!in)return false;
        unsigned count=unsigned(bytes[0])|unsigned(bytes[1])<<8|unsigned(bytes[2])<<16|unsigned(bytes[3])<<24;
        if(!in || count>100000)return false;
        Materials next;
        in.read(reinterpret_cast<char*>(next.portraits.data()),next.portraits.size());
        for(unsigned i=0;i<count && in;++i) {
            uint8_t header[8];std::array<uint8_t,64> mask;
            in.read(reinterpret_cast<char*>(header),8);
            in.read(reinterpret_cast<char*>(mask.data()),64);
            if(!in || header[0]>6 || header[1]!=128 || header[2]>15 || header[3]>15)return false;
            for(auto v:mask)if(v>=128 || (v&31)>19)return false;
            uint32_t hash=uint32_t(header[4])|uint32_t(header[5])<<8|uint32_t(header[6])<<16|uint32_t(header[7])<<24;
            if(!next.tiles.emplace(key(header[0],header[2],header[3],hash),mask).second)return false;
        }
        if(!in || in.peek()!=std::char_traits<char>::eof())return false;
        for(auto v:next.portraits)if(v>=128 || (v&31)>19)return false;
        *this=std::move(next);return true;
    }
};
}
