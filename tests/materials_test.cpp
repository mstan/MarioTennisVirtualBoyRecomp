#include "tennis_materials.h"
#include <cassert>
#include <iterator>
#include <string>
#include <vector>

int main(int argc,char** argv) {
    assert(argc==3);
    tennis::Materials catalog;
    assert(catalog.load(argv[1]) && !catalog.tiles.empty());
    const auto count=catalog.tiles.size();
    // Reviewed original-art landmarks: standing cap/hair/shirt/shorts, and
    // cap pixels in a side-facing swing. Hashes alone are insufficient: the
    // all-white CHR tile is used by both the red hat and the red shirt.
    struct Landmark {unsigned x,y,hash,u,v,material;};
    const Landmark landmarks[]={
        {8,8,0x7a9095b4u,7,1,2}, {8,10,0x1ff57941u,7,6,13},
        {8,12,0xd58f91f5u,0,3,19}, {8,13,0x8a304e94u,7,4,4},
        {8,8,0xd58f91f5u,0,1,2}, {8,9,0x833b5c19u,6,1,2}};
    for(const auto& point:landmarks) {
        auto it=catalog.tiles.find(tennis::Materials::key(0,point.x,point.y,point.hash));
        assert(it!=catalog.tiles.end());
        assert((it->second[point.v*8+point.u]&31)==point.material);
    }
    std::ifstream in(argv[1],std::ios::binary);
    const std::vector<char> original((std::istreambuf_iterator<char>(in)),{});
    auto reject=[&](std::vector<char> bytes) {
        {std::ofstream out(argv[2],std::ios::binary);out.write(bytes.data(),bytes.size());}
        assert(!catalog.load(argv[2]));
        assert(catalog.tiles.size()==count); // Failure preserves the previous catalog.
    };
    auto bytes=original;bytes[0]='?';reject(bytes);
    bytes=original;bytes.resize(10);reject(bytes);
    bytes=original;bytes.pop_back();reject(bytes);
    bytes=original;bytes.push_back(0);reject(bytes);
    bytes=original;bytes[8]=bytes[9]=bytes[10]=bytes[11]=char(255);reject(bytes);
    bytes=original;bytes[12]=31;reject(bytes); // Portrait material outside palette.
    bytes=original;bytes[12]=char(128);reject(bytes); // Reserved shade bit.
    bytes=original;bytes[12+7*1024]=7;reject(bytes); // Unknown character ID.
    bytes=original;bytes[12+7*1024+8]=31;reject(bytes); // Invalid tile material.
    assert(catalog.load(argv[1]));
    return 0;
}
