#include "tennis_materials.h"
#include <cassert>
#include <iterator>
#include <string>
#include <vector>

int main(int argc,char** argv) {
    assert(argc==4);
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
        {8,8,0xd58f91f5u,0,1,2}, {8,9,0x833b5c19u,6,1,2},
        // User-reported new-round pose: previously almost entirely red.
        {8,7,0x656ed016u,0,2,2}, {6,9,0x06fb002cu,1,5,3},
        {6,10,0xd5793f17u,4,0,13}, {8,10,0x6684933cu,7,7,19},
        {13,11,0xfaf62766u,2,2,6}, {6,13,0x6812d9c4u,4,2,4},
        {8,14,0x46a48e9du,4,7,5}};
    for(const auto& point:landmarks) {
        auto it=catalog.tiles.find(tennis::Materials::key(0,point.x,point.y,point.hash));
        assert(it!=catalog.tiles.end());
        assert((it->second[point.v*8+point.u]&31)==point.material);
    }
    // Recovery poses captured continuously, between the former TCP samples.
    struct ActorLandmark {unsigned c,x,y,hash,u,v,material;};
    const ActorLandmark recovery[]={
        {0,5,4,0x300189b0u,7,6,2}, {0,5,5,0xcd90f4bau,5,4,3},
        {0,5,6,0x26b8ca94u,2,6,4}, {1,5,6,0x0ff77f69u,7,3,8},
        {1,3,12,0xaecfd089u,5,6,6}, {1,6,12,0x0ccc0dc1u,7,5,4}};
    for(const auto& point:recovery) {
        auto it=catalog.tiles.find(tennis::Materials::key(point.c,point.x,point.y,point.hash));
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
    tennis::Materials hud;
    assert(hud.load(argv[3]));
    const Landmark lakitu[]={
        {2,1,0x9392ddadu,0,6,1}, {2,2,0x6e84d35eu,0,6,16},
        {3,0,0xd976ef9au,0,3,7}, {3,1,0x5860b881u,0,0,6},
        {3,1,0x5860b881u,4,2,8}, {5,0,0xdcfe9b1au,0,2,5}};
    for(const auto& point:lakitu) {
        auto it=hud.tiles.find(tennis::Materials::key(0,point.x,point.y,point.hash));
        assert(it!=hud.tiles.end());
        assert((it->second[point.v*8+point.u]&31)==point.material);
    }
    return 0;
}
