#pragma once

/*
 * Minimal protobuf wire format (proto3) for the scanner protocol: a reader that walks fields
 * and skips anything it doesn't know, and an append-only writer for Command. Schema and rules:
 * scanner_fw/proto/bletracker.proto and scanner_fw/PROTOCOL.md (protocol 3).
 */

#include <cstddef>
#include <cstdint>
#include <string>

namespace esphome {
namespace sector_scanner {
namespace pb {

enum WireType : uint8_t { VARINT = 0, FIXED64 = 1, LEN = 2, FIXED32 = 5 };

/* One field: number, wire type and either its varint value or its bytes (LEN, FIXED*) */
struct Field {
  uint32_t num{0};
  uint8_t wt{0};
  uint64_t v{0};
  const uint8_t *p{nullptr};
  size_t len{0};

  uint32_t u32() const { return (uint32_t) this->v; }
  int32_t s32() const { return (int32_t) ((uint32_t) (this->v >> 1) ^ (uint32_t) -(int32_t) (this->v & 1)); }
  bool b() const { return this->v != 0; }
};

/* Reads the fields of one message in order. next() is false at the end or on a malformed field
 * (then ok() is false too). Groups (wire types 3/4) are malformed: proto3 never sends them. */
class Reader {
 public:
  Reader(const uint8_t *p, size_t len) : p_(p), end_(p + len) {}
  explicit Reader(const Field &f) : p_(f.p), end_(f.p + f.len) {}

  bool next(Field &f) {
    if (this->p_ == this->end_ || !this->ok_)
      return false;
    uint64_t key;
    if (!this->varint_(key) || (key >> 3) == 0 || (key >> 3) > 0x1fffffff)
      return this->fail_();
    f.num = (uint32_t) (key >> 3);
    f.wt = key & 7;
    f.v = 0;
    f.p = nullptr;
    f.len = 0;
    switch (f.wt) {
      case VARINT:
        return this->varint_(f.v) || this->fail_();
      case FIXED64:
      case FIXED32: {
        size_t n = f.wt == FIXED64 ? 8 : 4;
        if ((size_t) (this->end_ - this->p_) < n)
          return this->fail_();
        f.p = this->p_;
        f.len = n;
        for (size_t i = 0; i < n; i++)
          f.v |= (uint64_t) this->p_[i] << (8 * i);
        this->p_ += n;
        return true;
      }
      case LEN: {
        uint64_t n;
        if (!this->varint_(n) || n > (uint64_t) (this->end_ - this->p_))
          return this->fail_();
        f.p = this->p_;
        f.len = (size_t) n;
        this->p_ += n;
        return true;
      }
      default:
        return this->fail_();
    }
  }
  bool ok() const { return this->ok_; }

 protected:
  bool varint_(uint64_t &out) {
    out = 0;
    for (int shift = 0; shift < 64; shift += 7) {
      if (this->p_ == this->end_)
        return false;
      uint8_t b = *this->p_++;
      out |= (uint64_t) (b & 0x7f) << shift;
      if (!(b & 0x80))
        return true;
    }
    return false;
  }
  bool fail_() {
    this->ok_ = false;
    return false;
  }

  const uint8_t *p_;
  const uint8_t *end_;
  bool ok_{true};
};

/* Walks a whole message and reports whether every field parsed (unknown ones included) */
inline bool well_formed(const uint8_t *p, size_t len) {
  Reader r(p, len);
  Field f;
  while (r.next(f)) {
  }
  return r.ok();
}

/* Append-only encoder, fields written in the order called (Command: ascending numbers) */
class Writer {
 public:
  void varint(uint64_t v) {
    while (v >= 0x80) {
      this->out.push_back((char) (v | 0x80));
      v >>= 7;
    }
    this->out.push_back((char) v);
  }
  void key(uint32_t num, WireType wt) { this->varint(((uint64_t) num << 3) | wt); }
  void u32(uint32_t num, uint32_t v) {
    this->key(num, VARINT);
    this->varint(v);
  }
  void boolean(uint32_t num, bool v) { this->u32(num, v ? 1 : 0); }
  void bytes(uint32_t num, const uint8_t *p, size_t len) {
    this->key(num, LEN);
    this->varint(len);
    this->out.append((const char *) p, len);
  }
  void message(uint32_t num, const Writer &sub) { this->bytes(num, (const uint8_t *) sub.out.data(), sub.out.size()); }

  std::string out;
};

}  // namespace pb
}  // namespace sector_scanner
}  // namespace esphome
