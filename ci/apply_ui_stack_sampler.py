"""Add a bounded user-stack sampler for backboardd and SpringBoard to the nabu UI watch.

Hardware evidence (XNU2LOG seq 1872): backboardd opens IOMFB, subscribes to notifications and receives
VSYNC, the Metal frontend passes every check and the scanout client serves (P4), yet backboardd never
calls swap_begin. The existing watch only reports the main thread's scheduler state, which does not say
where CoreAnimation's render server stops.

With nabu-ui-watch=1 (already in the installed boot arguments) every second sample, up to sample 40,
now also prints for backboardd and SpringBoard: the shared-region base and slide, and for each of up to
32 threads its scheduler state, user pc/lr/sp/fp and up to 24 frame-pointer return addresses.

Read-only: the sampler runs on the ESP log writer's kernel thread, references the threads under the
task lock, releases the lock, then reads user frames with vm_map_read_user (which may fault). No
scheduler, exec or VM policy changes. XNU APIs verified at xnu-10063.141.1 (d8b80295).
"""
import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
a = p.parse_args()
gen = a.source / 'scripts/nabu_ui_watch_source.py'
s = gen.read_text()

STACK_FN = r'''/* NABU_UI_STACK_V1: bounded read-only user stack sample of one task's threads.
 * Called from the ESP writer's kernel thread; no lock is held across user reads. */
#include <vm/vm_shared_region.h>
extern struct arm_saved_state *get_user_regs(thread_t);
extern void nabu_capture_append(const char *, unsigned);
static void
nabu_ui_stack_emit(const char *line, int bytes)
{
	if (bytes > 0 && bytes < 256) nabu_capture_append(line, (unsigned)bytes);
}
void
nabu_ui_watch_task_stacks(thread_t main_thread, int pid, unsigned sample, const char *name)
{
	enum { NABU_STACK_THREADS = 32, NABU_STACK_FRAMES = 24 };
	thread_t threads[NABU_STACK_THREADS];
	uint64_t frames[NABU_STACK_FRAMES];
	unsigned count = 0, total = 0;
	char line[256];
	if (main_thread == THREAD_NULL || name == NULL) return;
	task_t task = get_threadtask(main_thread);
	if (task == TASK_NULL || task == kernel_task) return;
	task_reference(task);
	vm_map_t map = VM_MAP_NULL;
	task_lock(task);
	if (task->active && task->map != VM_MAP_NULL) {
		thread_t t;
		queue_iterate(&task->threads, t, thread_t, task_threads) {
			total++;
			if (count < NABU_STACK_THREADS) {
				thread_reference(t);
				threads[count++] = t;
			}
		}
		map = task->map;
		vm_map_reference(map);
	}
	task_unlock(task);
	uint64_t slide = 0, base = 0;
	vm_shared_region_t sr = vm_shared_region_get(task);
	if (sr != NULL) {
		slide = (uint64_t)sr->sr_slide;
		base = (uint64_t)sr->sr_base_address;
		vm_shared_region_deallocate(sr);
	}
	nabu_ui_stack_emit(line, snprintf(line, sizeof(line),
	    "NabuStack: s=%u %s pid=%d threads=%u/%u sr_base=%llx sr_slide=%llx\n",
	    sample, name, pid, count, total, (unsigned long long)base, (unsigned long long)slide));
	for (unsigned i = 0; i < count; ++i) {
		thread_t t = threads[i];
		uint32_t state = 0, hint = 0;
		uint64_t wait = 0, pc = 0, lr = 0, sp = 0, fp = 0;
		(void)nabu_ui_watch_thread_state(t, &state, &hint, &wait);
		struct arm_saved_state *ss = get_user_regs(t);
		if (ss != NULL) {
			pc = (uint64_t)get_saved_state_pc(ss);
			lr = (uint64_t)get_saved_state_lr(ss);
			sp = (uint64_t)get_saved_state_sp(ss);
			fp = (uint64_t)get_saved_state_fp(ss);
		}
		unsigned nf = 0;
		uint64_t cur = fp;
		while (map != VM_MAP_NULL && nf < NABU_STACK_FRAMES && cur != 0 && (cur & 0x7) == 0 &&
		    cur < 0x0000008000000000ULL) {
			uint64_t pair[2] = {0, 0};
			if (vm_map_read_user(map, (vm_map_address_t)cur, pair, sizeof(pair)) != KERN_SUCCESS) break;
			uint64_t ret = pair[1] & 0x0000007fffffffffULL;
			if (ret == 0) break;
			frames[nf++] = ret;
			if (pair[0] <= cur) break;
			cur = pair[0];
		}
		nabu_ui_stack_emit(line, snprintf(line, sizeof(line),
		    "NabuStack: s=%u pid=%d tid=%llu st=%x h=%u w=%llx pc=%llx lr=%llx sp=%llx fp=%llx n=%u\n",
		    sample, pid, (unsigned long long)thread_tid(t), state, hint, (unsigned long long)wait,
		    (unsigned long long)(pc & 0x0000007fffffffffULL), (unsigned long long)(lr & 0x0000007fffffffffULL),
		    (unsigned long long)sp, (unsigned long long)fp, nf));
		for (unsigned f = 0; f < nf; f += 8) {
			int used = snprintf(line, sizeof(line), "NabuStack: s=%u tid=%llu f%u:", sample,
			    (unsigned long long)thread_tid(t), f);
			for (unsigned k = f; k < nf && k < f + 8 && used > 0 && used < 220; ++k) {
				used += snprintf(line + used, sizeof(line) - (unsigned)used, " %llx",
				    (unsigned long long)frames[k]);
			}
			if (used > 0 && used < 254) {
				line[used++] = '\n';
				line[used] = 0;
				nabu_ui_stack_emit(line, used);
			}
		}
		thread_deallocate(t);
	}
	if (map != VM_MAP_NULL) vm_map_deallocate(map);
	task_deallocate(task);
}
'''

def once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit('anchor drift: ' + what)
    return text.replace(old, new, 1)

if 'NABU_UI_STACK_V1' in s:
    raise SystemExit('stack sampler already applied')

# thread.c: THREAD_HELPER and the THREAD_PAIRS replacement both end the state helper with
# "\treturn 0;\n}\n"; append the stack sampler after it in both, so thread_source stays consistent.
if s.count('\treturn 0;\n}\n') != 2:
    raise SystemExit('anchor drift: thread helper end')
s = s.replace('\treturn 0;\n}\n', '\treturn 0;\n}\n' + STACK_FN)

# kern_exec.c: declaration and the call inside the per-target sample loop.
s = once(s, 'extern int nabu_ui_watch_thread_state(thread_t, uint32_t *, uint32_t *, uint64_t *);\n',
         'extern int nabu_ui_watch_thread_state(thread_t, uint32_t *, uint32_t *, uint64_t *);\n'
         'extern void nabu_ui_watch_task_stacks(thread_t, int, unsigned, const char *);\n', 'exec extern')
s = once(s, '''            exited, exited || latest_tid != slot->tid ||
            (state & (NABU_UI_TH_TERMINATE | NABU_UI_TH_TERMINATE2)), instances));
    }
''', '''            exited, exited || latest_tid != slot->tid ||
            (state & (NABU_UI_TH_TERMINATE | NABU_UI_TH_TERMINATE2)), instances));
        /* NABU_UI_STACK_V1: backboardd and SpringBoard user stacks, every second sample up to 40. */
        if (thread && !exited && i < 2 && (sample & 1) && sample <= 40)
            nabu_ui_watch_task_stacks(thread, slot->pid, sample, nabu_ui_names[i]);
    }
''', 'sample loop')
gen.write_text(s)
print('NABU_UI_STACK_SAMPLER_PATCH_PASS', gen)
