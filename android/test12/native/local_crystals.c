/* Exact-build offline addon. Runs on the game's existing UI owner thread.
 * No purchase records, receipts or Google callbacks are created.
 */
typedef unsigned int u32;
typedef u32 (*Message)(u32, u32, ...);
static u32 word(u32 p) { return *(const u32 *)p; }
static u32 field(u32 obj, u32 base, u32 offset) { return word(obj + word(base + offset)); }
static u32 text(u32 base, const char *s) {
    Message send = (Message)word(base + 0x105b7a0);
    return send(word(base + 0xe89000), word(base + 0xe802fc), s);
}
u32 setup(u32 self, u32 base) {
    if (!self) return self;
    u32 buttons = self + word(base + 0xf35268);
    u32 title = text(base, "ADD");
    for (unsigned i = 0; i < 4; ++i) {
        u32 b = word(buttons + i * 4);
        if (!b) continue;
        ((void (*)(u32,u32,u32))(base + 0xd10c30))(b, 0, title);
        ((void (*)(u32,u32,u32))(base + 0xd10fc4))(b, 0, 1);
    }
    u32 heading = field(self, base, 0xf35258);
    if (heading) ((void (*)(u32,u32,u32))(base + 0x526560))(heading, 0, text(base, "LOCAL CRYSTALS"));
    return self;
}
void grant(u32 self, u32 selector, u32 button, u32 base) {
    (void)selector;
    if (!self || !button) return;
    u32 buttons = self + word(base + 0xf35268);
    int quantity = 0;
    const int quantities[] = {200, 1200, 3000, 10000};
    for (unsigned i = 0; i < 4; ++i) if (word(buttons + i * 4) == button) quantity = quantities[i];
    if (!quantity) return;
    u32 manager = ((u32 (*)(u32,u32))(base + 0x9f3b14))(base + 0xe918e0, 0);
    if (!manager) return;
    int old = ((int (*)(u32,u32))(base + 0x9f452c))(manager, 0);
    // Bound arithmetic and stop excessive taps without wrapping the saved int.
    if (old < 0 || old > 10000000 - quantity) return;
    Message send = (Message)word(base + 0x105b7a0);
    u32 input = send(word(base + 0xe89000), word(base + 0xe800c8), base + 0xf96bf8, old + quantity + 73);
    u32 check = send(input, word(base + 0xe80408));
    if (!check) return;
    // modify subtracts its argument and verifies its usual local consistency
    // string. Keep its watcher notification, amountString and needsSave path.
    ((void (*)(u32,u32,int,u32))(base + 0x9f4f74))(manager, 0, -quantity, check);
    ((void (*)(u32,u32))(base + 0x9f4568))(manager, 0);
    ((void (*)(u32,u32,u32))(base + 0xb611c0))(self, 0, button);
}
