// gc_mylib.h - corresponds to mycpp/mylib.py

#ifndef MYCPP_GC_MYLIB_H
#define MYCPP_GC_MYLIB_H

template <class K, class V>
class Dict;

// https://stackoverflow.com/questions/3919995/determining-sprintf-buffer-size-whats-the-standard/11092994#11092994
// Notes:
// - Python 2.7's intobject.c has an erroneous +6
// - This is 13, but len('-2147483648') is 11, which means we only need 12?
// - This formula is valid for octal(), because 2^(3 bits) = 8

const int kIntBufSize = CHAR_BIT * sizeof(int) / 3 + 3;

namespace mylib {

Tuple2<Str*, Str*> split_once(Str* s, Str* delim);

// Used by generated _build/cpp/osh_eval.cc
inline Str* StrFromC(const char* s) {
  return ::StrFromC(s);
}

template <typename K, typename V>
void dict_erase(Dict<K, V>* haystack, K needle) {
  int pos = haystack->position_of_key(needle);
  if (pos == -1) {
    return;
  }
  haystack->entry_->items_[pos] = kDeletedEntry;
  // Zero out for GC.  These could be nullptr or 0
  haystack->keys_->items_[pos] = 0;
  haystack->values_->items_[pos] = 0;
  haystack->len_--;
}

// NOTE: Can use OverAllocatedStr for all of these, rather than copying

inline Str* hex_lower(int i) {
  char buf[kIntBufSize];
  int len = snprintf(buf, kIntBufSize, "%x", i);
  return ::StrFromC(buf, len);
}

inline Str* hex_upper(int i) {
  char buf[kIntBufSize];
  int len = snprintf(buf, kIntBufSize, "%X", i);
  return ::StrFromC(buf, len);
}

inline Str* octal(int i) {
  char buf[kIntBufSize];
  int len = snprintf(buf, kIntBufSize, "%o", i);
  return ::StrFromC(buf, len);
}

class LineReader : Obj {
 public:
  // Abstract type with no fields: unknown size
  LineReader(uint16_t field_mask, int obj_len)
      : Obj(Tag::FixedSize, field_mask, obj_len) {
  }
  virtual Str* readline() = 0;
  virtual bool isatty() {
    return false;
  }
  virtual int fileno() {
    NotImplemented();  // Uncalled
  }
};

class BufLineReader : public LineReader {
 public:
  explicit BufLineReader(Str* s);
  virtual Str* readline();

  Str* s_;
  int pos_;

  DISALLOW_COPY_AND_ASSIGN(BufLineReader)
};

constexpr uint16_t maskof_BufLineReader() {
  return maskbit_v(offsetof(BufLineReader, s_));
}

inline BufLineReader::BufLineReader(Str* s)
    : LineReader(maskof_BufLineReader(), sizeof(BufLineReader)),
      s_(s),
      pos_(0) {
}

// Wrap a FILE*
class CFileLineReader : public LineReader {
 public:
  explicit CFileLineReader(FILE* f);
  virtual Str* readline();
  virtual int fileno() {
    return ::fileno(f_);
  }

 private:
  FILE* f_;

  DISALLOW_COPY_AND_ASSIGN(CFileLineReader)
};

inline CFileLineReader::CFileLineReader(FILE* f)
    : LineReader(kZeroMask, sizeof(CFileLineReader)), f_(f) {
}

extern LineReader* gStdin;

inline LineReader* Stdin() {
  if (gStdin == nullptr) {
    gStdin = Alloc<CFileLineReader>(stdin);
  }
  return gStdin;
}

LineReader* open(Str* path);

class Writer : public Obj {
 public:
  Writer(uint8_t heap_tag, uint16_t field_mask, int obj_len)
      : Obj(heap_tag, field_mask, obj_len) {
  }
  virtual void write(Str* s) = 0;
  virtual void flush() = 0;
  virtual bool isatty() = 0;
};

class MutableStr;

class Buf {
 public:
  // The initial capacity is big enough for a line
  Buf(int cap);
  void Extend(Str* s);

 private:
  friend class BufWriter;
  friend Str* StrFromBuf(Buf*);
  friend Buf* NewBuf(int);

  char* data();
  char* end();
  int capacity();

  MutableStr* str_;
  int len_;

  /*
  // TODO: move this state into BufWriter
  int len_;  // data length, not including NUL
  int cap_;  // capacity, not including NUL
  char data_[1];
  */
};

Str* StrFromBuf(Buf*);
Buf* NewBuf(int);

constexpr uint16_t maskof_BufWriter();

class BufWriter : public Writer {
 public:
  BufWriter() : Writer(Tag::FixedSize, maskof_BufWriter(), sizeof(BufWriter)), buf_(0) {
  }
  void write(Str* s) override;
  void flush() override {
  }
  bool isatty() override {
    return false;
  }
  // For cStringIO API
  Str* getvalue();

 private:
  friend constexpr uint16_t maskof_BufWriter();
  void EnsureCapacity(int n);

  Buf buf_;
  bool is_valid_ = true;  // It becomes invalid after getvalue() is called
};

constexpr uint16_t maskof_BufWriter() {
  // maskvit_v() because BufWriter has virtual methods
  return maskbit_v(offsetof(BufWriter, buf_));
}

class FormatStringer {
 public:
  FormatStringer() : data_(nullptr), len_(0) {
  }
  Str* getvalue();

  // Called before reusing the global gBuf instance for fmtX() functions
  //
  // Problem with globals: '%r' % obj will recursively call asdl/format.py,
  // which has its own % operations
  void reset() {
    if (data_) {
      free(data_);
    }
    data_ = nullptr;  // arg to next realloc()
    len_ = 0;
  }

  // Note: we do NOT need to instantiate a Str() to append
  void write_const(const char* s, int len);

  // strategy: snprintf() based on sizeof(int)
  void format_d(int i);
  void format_o(int i);
  void format_s(Str* s);
  void format_r(Str* s);  // formats with quotes

  // looks at arbitrary type tags?  Is this possible
  // Passes "this" to functions generated by ASDL?
  void format_r(void* s);

 private:
  // Just like a string, except it's mutable
  char* data_;
  int len_;
};

// Wrap a FILE*
class CFileWriter : public Writer {
 public:
  explicit CFileWriter(FILE* f)
      : Writer(Tag::FixedSize, kZeroMask, sizeof(BufWriter)), f_(f) {
  }
  void write(Str* s) override;
  void flush() override;
  bool isatty() override;

 private:
  FILE* f_;

  DISALLOW_COPY_AND_ASSIGN(CFileWriter)
};

extern Writer* gStdout;

inline Writer* Stdout() {
  if (gStdout == nullptr) {
    // TODO: global instance needs rooting
    gStdout = Alloc<CFileWriter>(stdout);
  }
  return gStdout;
}

extern Writer* gStderr;

inline Writer* Stderr() {
  if (gStderr == nullptr) {
    // TODO: global instance needs rooting
    gStderr = Alloc<CFileWriter>(stderr);
  }
  return gStderr;
}

}  // namespace mylib

extern mylib::FormatStringer gBuf;

#endif  // MYCPP_GC_MYLIB_H
