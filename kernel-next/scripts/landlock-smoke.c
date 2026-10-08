#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/landlock.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

static void check(int ok, const char *name)
{
    printf("CHECK %s %s errno=%d\n", name, ok ? "PASS" : "FAIL", errno);
    fflush(stdout);
    if (!ok) exit(1);
}

static void read_text(const char *path, char *buf, size_t size)
{
    int fd = open(path, O_RDONLY);
    check(fd >= 0, path);
    ssize_t n = read(fd, buf, size - 1);
    check(n >= 0, "read_text");
    buf[n] = 0;
    close(fd);
}

static int can_read(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -errno;
    close(fd);
    return 0;
}

static void child_test(void)
{
    int group = open("/sys/fs/cgroup/landlock-smoke/cgroup.procs", O_WRONLY);
    check(group >= 0, "open_nonroot_cpu_cgroup");
    check(write(group, "0", 1) == 1, "enter_nonroot_cpu_cgroup");
    close(group);
    struct rlimit rtprio = {1, 1};
    check(setrlimit(RLIMIT_RTPRIO, &rtprio) == 0, "set_test_rtprio_limit");
    check(setgid(1000) == 0 && setuid(1000) == 0, "unprivileged_uid_1000");
    struct sched_param rr = {.sched_priority = 1};
    check(sched_setscheduler(0, SCHED_RR, &rr) == 0, "unprivileged_rr_with_rt_group_sched_0");
    rr.sched_priority = 0;
    check(sched_setscheduler(0, SCHED_OTHER, &rr) == 0, "restore_normal_scheduler");
    check(can_read("/tmp/allowed/data") == 0, "allowed_read_before_sandbox");
    check(can_read("/tmp/denied/data") == 0, "denied_read_before_sandbox");

    struct landlock_ruleset_attr ruleset = {
        .handled_access_fs = LANDLOCK_ACCESS_FS_READ_FILE |
                             LANDLOCK_ACCESS_FS_WRITE_FILE,
    };
    int ruleset_fd = syscall(__NR_landlock_create_ruleset, &ruleset, sizeof(ruleset), 0);
    check(ruleset_fd >= 0, "create_ruleset_unprivileged");
    int parent = open("/tmp/allowed", O_PATH | O_CLOEXEC);
    check(parent >= 0, "open_allowed_parent");
    struct landlock_path_beneath_attr rule = {
        .allowed_access = ruleset.handled_access_fs,
        .parent_fd = parent,
    };
    check(syscall(__NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, &rule, 0) == 0,
          "add_allow_rule");
    close(parent);
    check(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0, "no_new_privileges");
    check(syscall(__NR_landlock_restrict_self, ruleset_fd, 0) == 0, "enforce_ruleset");
    close(ruleset_fd);
    check(can_read("/tmp/allowed/data") == 0, "allowed_read_after_sandbox");
    check(can_read("/tmp/denied/data") == -EACCES, "deny_read_EACCES");
    int fd = open("/tmp/allowed/data", O_WRONLY);
    check(fd >= 0, "allowed_write_after_sandbox");
    close(fd);
    fd = open("/tmp/denied/data", O_WRONLY);
    check(fd < 0 && errno == EACCES, "deny_write_EACCES");
    puts("LANDLOCK_UNPRIVILEGED_ENFORCEMENT_PASS");
}

int main(int argc, char **argv)
{
    int expect_disabled = argc == 2 && !strcmp(argv[1], "--expect-disabled");
    char text[8192];
    struct utsname u;
    check(uname(&u) == 0, "uname");
    printf("KERNEL_RELEASE %s\n", u.release);
    check(expect_disabled ? !strcmp(u.release, "6.18.44-current-rockchip64") :
          strstr(u.release, "-current-rockchip64-landlock1") != NULL, "correct_test_kernel");
    read_text("/sys/kernel/security/lsm", text, sizeof(text));
    printf("ACTIVE_LSM %s\n", text);
    check(expect_disabled ? strstr(text, "landlock") == NULL : strstr(text, "landlock") != NULL,
          "landlock_expected_default_lsm_state");
    read_text("/proc/cmdline", text, sizeof(text));
    printf("KERNEL_CMDLINE %s", text);
    check(strstr(text, "rt_group_sched=0") != NULL, "tested_rt_boot_parameter");
    check(strstr(text, "lsm=") == NULL, "no_lsm_commandline_override");
    read_text("/proc/sys/kernel/sched_rt_runtime_us", text, sizeof(text));
    check(strtol(text, NULL, 10) == 950000, "rt_runtime_950000_preserved");
    read_text("/proc/sys/kernel/sched_rt_period_us", text, sizeof(text));
    check(strtol(text, NULL, 10) == 1000000, "rt_period_1000000_preserved");
    int abi = syscall(__NR_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    int abi_errno = errno;
    printf("LANDLOCK_ABI %d\n", abi);
    if (expect_disabled) {
        check(abi == -1 && abi_errno == ENOSYS, "original_kernel_landlock_ENOSYS");
        puts("ORIGINAL_KERNEL_LANDLOCK_NEGATIVE_CONTROL_PASS");
        return 0;
    }
    check(abi >= 1, "landlock_abi_available");
    const char *paths[] = {"/tmp/allowed/data", "/tmp/denied/data"};
    mkdir("/tmp/allowed", 0777);
    mkdir("/tmp/denied", 0777);
    for (int i = 0; i < 2; i++) {
        int fd = open(paths[i], O_CREAT | O_RDWR | O_TRUNC, 0666);
        check(fd >= 0, "create_fixture");
        check(fchown(fd, 1000, 1000) == 0, "set_fixture_owner");
        check(write(fd, "ok\n", 3) == 3, "write_fixture");
        close(fd);
    }
    pid_t pid = fork();
    check(pid >= 0, "fork_unprivileged_test");
    if (!pid) {
        child_test();
        return 0;
    }
    int status;
    check(waitpid(pid, &status, 0) == pid, "wait_child");
    check(WIFEXITED(status) && WEXITSTATUS(status) == 0, "child_enforcement_result");
    puts("ROCK5T_KERNEL_QEMU_SMOKE_PASS");
    return 0;
}
