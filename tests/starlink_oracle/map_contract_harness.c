/* Executed after the actual map_require_contract/map_snapshot_fault_free C.
 * Golden legacy register contracts and explicit experimental ABI 1.5/1.6.
 */
int main(void)
{
    static const u32 expected[][7] = {
        {0x10001, 15, 0x3f, 0, 0, 0, 0x17ff},
        {0x10002, 30, 0x7f, 0x000f0203, 7, 1073744004, 0x37ff},
        {0x10003, 60, 0x7f, 0x020f0403, 21, 1073765335, 0x37ff},
        {0x10004, 60, 0xff, 0x020f0403, 21, 1073765335, 0x37ff},
        {0x10005, 15, 0x13f, 0x000f0202, 0, 0, 0x57ff},
        {0x10006, 15, 0x33f, 0x000f0202, 0, 0, 0x57ff},
    };
    static const u32 contract30[8] = {
        0x73142604, 0x7077b036, 0xf9213db3, 0x574e4a55,
        0x6fd424b9, 0x7a293843, 0xbd6ee085, 0xc2bf33af,
    };
    static const u32 contract60[8] = {
        0x8e807d15, 0xd5372b0a, 0x9669d119, 0x0d899697,
        0xe7c2911a, 0x73ddfb23, 0x095806c2, 0xa31de5b2,
    };
    static const u32 rejected[] = {0, 1, 0x10000, 0x10007, 0x20000};
    struct adi_starlink_pss_map st;
    struct map_snapshot snapshot;
    unsigned int row, bit, field, mutations = 0, health_cases = 0;
    assert(MAP_MIN_VERSION == 0x10001 && MAP_MAX_VERSION == 0x10006);
    for (row = 0; row < ARRAY_SIZE(expected); row++) {
        const u32 *gold = expected[row];
        memset(&st, 0, sizeof(st));
        st.version = gold[0];
        st.mmio[MAP_REG_CAPABILITIES / 4] = gold[2];
        st.mmio[MAP_REG_INPUT_RATE_MSPS / 4] = gold[1];
        st.mmio[MAP_REG_DDC_CONFIG / 4] = gold[3];
        st.mmio[MAP_REG_DDC_GROUP_DELAY / 4] = gold[4];
        st.mmio[MAP_REG_COEFFICIENT_ENERGY / 4] = gold[5];
        if (gold[1] != 15)
            memcpy(&st.mmio[MAP_REG_DDC_CONTRACT_0 / 4],
                   gold[1] == 30 ? contract30 : contract60, sizeof(contract30));
        assert(map_require_contract(&st) == 0 && st.input_rate_msps == gold[1]);
        /* Every capability bit, not just absence of the new shared bit. */
        for (bit = 0; bit < 32; bit++) {
            st.mmio[MAP_REG_CAPABILITIES / 4] ^= UINT32_C(1) << bit;
            assert(map_require_contract(&st) == -EINVAL);
            st.mmio[MAP_REG_CAPABILITIES / 4] ^= UINT32_C(1) << bit;
            mutations++;
        }
        if (row != 0) {
            unsigned int end = gold[1] == 15 ? MAP_REG_DDC_GROUP_DELAY :
                MAP_REG_DDC_CONTRACT_0 + 7 * 4;
            for (field = MAP_REG_INPUT_RATE_MSPS; field <= end; field += 4) {
                for (bit = 0; bit < 32; bit++) {
                    st.mmio[field / 4] ^= UINT32_C(1) << bit;
                    assert(map_require_contract(&st) == -EINVAL);
                    st.mmio[field / 4] ^= UINT32_C(1) << bit;
                    mutations++;
                }
            }
        }
        memset(&snapshot, 0, sizeof(snapshot));
        assert(map_snapshot_fault_free(&st, &snapshot));
        for (field = 0; field < ARRAY_SIZE(snapshot.fault_signature); field++) {
            for (bit = 0; bit < 32; bit++) {
                u32 flag = UINT32_C(1) << bit;
                snapshot.fault_signature[field] = flag;
                assert(map_snapshot_fault_free(&st, &snapshot) ==
                       (field == 7 && !(flag & gold[6])));
                snapshot.fault_signature[field] = 0;
                health_cases++;
            }
        }
    }
    for (row = 0; row < ARRAY_SIZE(rejected); row++) {
        st.version = rejected[row];
        assert(map_require_contract(&st) == -EINVAL);
    }
    printf("MAP_DRIVER_CONTRACT_HEALTH_PASS versions=6 mutations=%u health_cases=%u\n",
           mutations, health_cases);
    return 0;
}
