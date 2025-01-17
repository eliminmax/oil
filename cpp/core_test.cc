#include "cpp/core.h"

#include <errno.h>        // errno
#include <fcntl.h>        // O_RDWR
#include <signal.h>       // SIG*, kill()
#include <sys/utsname.h>  // uname
#include <unistd.h>       // getpid(), getuid(), environ

#include "cpp/core_error.h"
#include "cpp/stdlib.h"         // posix::getcwd
#include "mycpp/gc_builtins.h"  // IOError_OSError
#include "vendor/greatest.h"

static_assert(offsetof(Obj, field_mask_) == offsetof(error::Usage, field_mask_),
              "Invalid layout");
static_assert(offsetof(Obj, field_mask_) ==
                  offsetof(error::_ErrorWithLocation, field_mask_),
              "Invalid layout");

TEST exceptions_test() {
  bool caught = false;
  try {
    throw Alloc<error::Usage>(StrFromC("msg"), 42);
  } catch (error::Usage* e) {
    log("e %p", e);
    gHeap.RootInCurrentFrame(e);
    caught = true;
  }

  ASSERT(caught);

  PASS();
}

TEST environ_test() {
  Dict<Str*, Str*>* env = pyos::Environ();
  Str* p = env->get(StrFromC("PATH"));
  ASSERT(p != nullptr);
  log("PATH = %s", p->data_);

  PASS();
}

TEST user_home_dir_test() {
  uid_t uid = getuid();
  Str* username = pyos::GetUserName(uid);
  ASSERT(username != nullptr);

  Str* dir0 = pyos::GetMyHomeDir();
  ASSERT(dir0 != nullptr);

  Str* dir1 = pyos::GetHomeDir(username);
  ASSERT(dir1 != nullptr);

  ASSERT(str_equals(dir0, dir1));

  PASS();
}

TEST uname_test() {
  Str* os_type = pyos::OsType();
  ASSERT(os_type != nullptr);

  utsname un = {};
  ASSERT(uname(&un) == 0);
  ASSERT(str_equals(StrFromC(un.sysname), os_type));

  PASS();
}

TEST pyos_readbyte_test() {
  // Write 2 bytes to this file
  const char* tmp_name = "pyos_ReadByte";
  int fd = ::open(tmp_name, O_CREAT | O_RDWR, 0644);
  if (fd < 0) {
    printf("1. ERROR %s\n", strerror(errno));
  }
  ASSERT(fd > 0);
  write(fd, "SH", 2);
  close(fd);

  fd = ::open(tmp_name, O_CREAT | O_RDWR, 0644);
  if (fd < 0) {
    printf("2. ERROR %s\n", strerror(errno));
  }

  Tuple2<int, int> tup = pyos::ReadByte(fd);
  ASSERT_EQ_FMT(0, tup.at1(), "%d");  // error code
  ASSERT_EQ_FMT('S', tup.at0(), "%d");

  tup = pyos::ReadByte(fd);
  ASSERT_EQ_FMT(0, tup.at1(), "%d");  // error code
  ASSERT_EQ_FMT('H', tup.at0(), "%d");

  tup = pyos::ReadByte(fd);
  ASSERT_EQ_FMT(0, tup.at1(), "%d");  // error code
  ASSERT_EQ_FMT(pyos::EOF_SENTINEL, tup.at0(), "%d");

  close(fd);

  PASS();
}

TEST pyos_read_test() {
  const char* tmp_name = "pyos_Read";
  int fd = ::open(tmp_name, O_CREAT | O_RDWR, 0644);
  if (fd < 0) {
    printf("3. ERROR %s\n", strerror(errno));
  }
  ASSERT(fd > 0);
  write(fd, "SH", 2);
  close(fd);

  // open needs an absolute path for some reason?  _tmp/pyos doesn't work
  fd = ::open(tmp_name, O_CREAT | O_RDWR, 0644);
  if (fd < 0) {
    printf("4. ERROR %s\n", strerror(errno));
  }

  List<Str*>* chunks = NewList<Str*>();
  Tuple2<int, int> tup = pyos::Read(fd, 4096, chunks);
  ASSERT_EQ_FMT(2, tup.at0(), "%d");  // error code
  ASSERT_EQ_FMT(0, tup.at1(), "%d");
  ASSERT_EQ_FMT(1, len(chunks), "%d");

  tup = pyos::Read(fd, 4096, chunks);
  ASSERT_EQ_FMT(0, tup.at0(), "%d");  // error code
  ASSERT_EQ_FMT(0, tup.at1(), "%d");
  ASSERT_EQ_FMT(1, len(chunks), "%d");

  close(fd);

  PASS();
}

TEST pyos_test() {
  // This test isn't hermetic but it should work in most places, including in a
  // container

  Str* current = posix::getcwd();

  int err_num = pyos::Chdir(StrFromC("/"));
  ASSERT(err_num == 0);

  err_num = pyos::Chdir(StrFromC("/nonexistent__"));
  ASSERT(err_num != 0);

  err_num = pyos::Chdir(current);
  ASSERT(err_num == 0);

  PASS();
}

TEST pyutil_test() {
  // OK this seems to work
  Str* escaped = pyutil::BackslashEscape(StrFromC("'foo bar'"), StrFromC(" '"));
  ASSERT(str_equals(escaped, StrFromC("\\'foo\\ bar\\'")));

  Str* escaped2 = pyutil::BackslashEscape(StrFromC(""), StrFromC(" '"));
  ASSERT(str_equals(escaped2, StrFromC("")));

  Str* s = pyutil::ChArrayToString(NewList<int>({65}));
  ASSERT(str_equals(s, StrFromC("A")));
  ASSERT_EQ_FMT(1, len(s), "%d");

  Str* s2 = pyutil::ChArrayToString(NewList<int>({102, 111, 111}));
  ASSERT(str_equals(s2, StrFromC("foo")));
  ASSERT_EQ_FMT(3, len(s2), "%d");

  Str* s3 = pyutil::ChArrayToString(NewList<int>({45, 206, 188, 45}));
  ASSERT(str_equals(s3, StrFromC("-\xce\xbc-")));  // mu char
  ASSERT_EQ_FMT(4, len(s3), "%d");

  PASS();
}

TEST strerror_test() {
  IOError_OSError err(EINVAL);
  Str* s1 = pyutil::strerror(&err);
  ASSERT(s1 != nullptr);

  Str* s2 = StrFromC(strerror(EINVAL));
  ASSERT(s2 != nullptr);

  ASSERT(str_equals(s1, s2));

  PASS();
}

TEST signal_test() {
  pyos::InitShell();

  {
    // Approximate TrapState::TakeRunList()
    RootsFrame _r;
    List<int>* q = pyos::TakeSignalQueue();
    ASSERT(q != nullptr);
    ASSERT(len(q) == 0);
  }

  pid_t mypid = getpid();

  pyos::RegisterSignalInterest(SIGUSR1);
  pyos::RegisterSignalInterest(SIGUSR2);
  kill(mypid, SIGUSR1);
  ASSERT(pyos::LastSignal() == SIGUSR1);
  kill(mypid, SIGUSR2);
  ASSERT(pyos::LastSignal() == SIGUSR2);

  {
    // Approximate TrapState::TakeRunList()
    RootsFrame _r;
    List<int>* q = pyos::TakeSignalQueue();
    ASSERT(q != nullptr);
    ASSERT(len(q) == 2);
    ASSERT(q->index_(0) == SIGUSR1);
    ASSERT(q->index_(1) == SIGUSR2);
  }

  pyos::Sigaction(SIGUSR1, SIG_IGN);
  kill(mypid, SIGUSR1);
  {
    // Approximate TrapState::TakeRunList()
    RootsFrame _r;
    List<int>* q = pyos::TakeSignalQueue();
    ASSERT(q != nullptr);
    ASSERT(len(q) == 0);
  }
  pyos::Sigaction(SIGUSR2, SIG_IGN);

  pyos::RegisterSignalInterest(SIGWINCH);
  kill(mypid, SIGWINCH);
  ASSERT(pyos::LastSignal() == pyos::UNTRAPPED_SIGWINCH);
  pyos::SetSigwinchCode(SIGWINCH);
  kill(mypid, SIGWINCH);
  ASSERT(pyos::LastSignal() == SIGWINCH);
  {
    // Approximate TrapState::TakeRunList()
    RootsFrame _r;
    List<int>* q = pyos::TakeSignalQueue();
    ASSERT(q != nullptr);
    ASSERT(len(q) == 2);
    ASSERT(q->index_(0) == SIGWINCH);
    ASSERT(q->index_(1) == SIGWINCH);
  }

  PASS();
}

GREATEST_MAIN_DEFS();

int main(int argc, char** argv) {
  gHeap.Init();

  GREATEST_MAIN_BEGIN();

  RUN_TEST(exceptions_test);
  RUN_TEST(environ_test);
  RUN_TEST(user_home_dir_test);
  RUN_TEST(uname_test);
  RUN_TEST(pyos_readbyte_test);
  RUN_TEST(pyos_read_test);
  RUN_TEST(pyos_test);  // non-hermetic
  RUN_TEST(pyutil_test);
  RUN_TEST(strerror_test);
  RUN_TEST(signal_test);

  gHeap.CleanProcessExit();

  GREATEST_MAIN_END(); /* display results */
  return 0;
}
