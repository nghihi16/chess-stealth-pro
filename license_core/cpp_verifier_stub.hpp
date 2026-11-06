#pragma once
// ============================================================================
// CHESS STEALTH PRO — STATIC C++ LICENSE CORE HEADER (NO EXTERNAL DLL)
// Dùng khi bạn chuyển phần Core sang C++ (Compile static trực tiếp vào .exe)
// ============================================================================

#include <array>
#include <cstdint>
#include <string>

namespace chess_stealth {

// Ed25519 Public Key (32 bytes) khớp 100% với license_core/crypto_ed25519.py
// Nhúng cứng dưới dạng mảng byte XOR để không lộ chuỗi hex khi dùng strings/IDA.
constexpr std::array<uint8_t, 32> OBFS_ED25519_PUBKEY = {
    0x98, 0x05, 0x8F, 0x3D, 0x41, 0x7A, 0x19, 0xE2,
    0x55, 0xC1, 0x08, 0xB4, 0x77, 0x2E, 0x9A, 0xF0,
    0x12, 0x6D, 0x83, 0x4C, 0xB9, 0x31, 0xE7, 0x04,
    0x5A, 0xDF, 0x28, 0x90, 0x63, 0x1B, 0x7C, 0xA5
};

// Hàm tính hệ số tỷ lệ mũi tên rải rác trong vòng lặp đồ họa (Inlined)
// Nếu trạng thái chữ ký Ed25519 chưa hợp lệ, trả về 0.0f làm mũi tên tự tiêu biến.
__forceinline float compute_arrow_scale_gate(uint32_t session_magic) noexcept {
    // Giá trị magic 0x5A8F19E2 chỉ được ghi vào RAM sau khi Ed25519 verify thành công
    return (session_magic == 0x5A8F19E2u) ? 1.0f : 0.0f;
}

} // namespace chess_stealth
