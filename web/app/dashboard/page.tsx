"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import Shell, { useMe } from "@/components/shell";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  Spinner,
  StatusChip,
} from "@/components/ui";
import {
  createMeeting,
  createOrg,
  createProject,
  listMeetings,
  listProjects,
} from "@/lib/api";
import type { Meeting } from "@/lib/types";

interface ProjectRow {
  id: string;
  org_id: string;
  name: string;
  my_role?: string;
}

export default function DashboardPage() {
  return (
    <Shell>
      <Dashboard />
    </Shell>
  );
}

function Dashboard() {
  const { me, orgId, refresh } = useMe();
  const [projects, setProjects] = useState<ProjectRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");

  const loadProjects = useCallback(async () => {
    if (!orgId) return;
    try {
      const rows = await listProjects(orgId);
      setProjects(rows);
      setSelected((prev) =>
        prev && rows.some((r) => r.id === prev) ? prev : (rows[0]?.id ?? null),
      );
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
      setProjects([]);
    }
  }, [orgId]);

  useEffect(() => {
    setProjects(null);
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (!selected) {
      setMeetings(null);
      return;
    }
    setMeetings(null);
    listMeetings(selected)
      .then(setMeetings)
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load meetings");
        setMeetings([]);
      });
  }, [selected]);

  const project = useMemo(
    () => projects?.find((p) => p.id === selected) ?? null,
    [projects, selected],
  );
  const canHost =
    project?.my_role === "manager" || project?.my_role === "admin";

  const onCreateMeeting = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !title.trim()) return;
    setCreating(true);
    try {
      const m = await createMeeting(selected, title.trim());
      setMeetings((prev) => [m, ...(prev ?? [])]);
      setTitle("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create meeting");
    } finally {
      setCreating(false);
    }
  };

  if (!orgId) return <FirstRun onDone={refresh} />;

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-[220px_1fr]">
      {/* project rail */}
      <aside>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-xs font-medium uppercase tracking-wider text-faint">
            Projects
          </h2>
          <NewProjectButton orgId={orgId} onCreated={loadProjects} me={me} />
        </div>
        {projects === null ? (
          <Spinner />
        ) : projects.length === 0 ? (
          <p className="text-xs text-faint">No projects yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {projects.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => setSelected(p.id)}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                    selected === p.id
                      ? "bg-raised text-ink"
                      : "text-muted hover:bg-hover hover:text-ink"
                  }`}
                >
                  {p.name}
                  {p.my_role && (
                    <span className="ml-2 font-mono text-[10px] uppercase text-faint">
                      {p.my_role}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
        {project && (
          <div className="mt-6 space-y-1 border-t border-edge pt-4">
            <Link
              href={`/projects/${project.id}/brief`}
              className="block rounded-md px-3 py-1.5 text-sm text-muted hover:bg-hover hover:text-ink"
            >
              Pre-meeting brief
            </Link>
            <Link
              href={`/projects/${project.id}/actions`}
              className="block rounded-md px-3 py-1.5 text-sm text-muted hover:bg-hover hover:text-ink"
            >
              Action tracker
            </Link>
          </div>
        )}
      </aside>

      {/* meetings */}
      <section>
        {error && (
          <div className="mb-4">
            <ErrorBanner message={error} />
          </div>
        )}
        {project && (
          <>
            <div className="mb-4 flex items-center justify-between">
              <h1 className="text-lg font-semibold text-ink">{project.name}</h1>
              {canHost && (
                <form onSubmit={onCreateMeeting} className="flex gap-2">
                  <Input
                    placeholder="New meeting title…"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-56"
                  />
                  <Button type="submit" disabled={creating || !title.trim()}>
                    {creating ? "Creating…" : "Create"}
                  </Button>
                </form>
              )}
            </div>

            {meetings === null ? (
              <Spinner label="Loading meetings…" />
            ) : meetings.length === 0 ? (
              <EmptyState
                title="No meetings in this project yet"
                hint={
                  canHost
                    ? "Create one above — recording and transcription are automatic."
                    : "A project manager can schedule the first meeting."
                }
              />
            ) : (
              <ul className="space-y-2">
                {meetings.map((m) => (
                  <li key={m.id}>
                    <Card className="flex items-center gap-4 px-4 py-3">
                      <div className="min-w-0 flex-1">
                        <Link
                          href={`/meetings/${m.id}`}
                          className="block truncate text-sm font-medium text-ink hover:text-accent"
                        >
                          {m.title}
                        </Link>
                        <p className="mt-0.5 font-mono text-[11px] text-faint">
                          {m.started_at
                            ? new Date(m.started_at).toLocaleString()
                            : "not started"}
                        </p>
                      </div>
                      <StatusChip status={m.status} />
                      {(m.status === "scheduled" || m.status === "live") && (
                        <Link href={`/room/${m.id}`}>
                          <Button
                            variant={m.status === "live" ? "primary" : "ghost"}
                          >
                            Join
                          </Button>
                        </Link>
                      )}
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function NewProjectButton({
  orgId,
  onCreated,
  me,
}: {
  orgId: string;
  onCreated: () => Promise<void>;
  me: { orgs: { org_id: string; role: string }[] };
}) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const isAdmin = me.orgs.some((o) => o.org_id === orgId && o.role === "admin");
  if (!isAdmin) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await createProject(orgId, name.trim()).catch(() => undefined);
    setName("");
    setOpen(false);
    await onCreated();
  };

  return open ? (
    <form onSubmit={submit} className="flex gap-1">
      <Input
        autoFocus
        placeholder="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={() => !name && setOpen(false)}
        className="h-7 w-28 px-2 py-1 text-xs"
      />
    </form>
  ) : (
    <button
      onClick={() => setOpen(true)}
      className="text-xs text-faint hover:text-accent"
    >
      + new
    </button>
  );
}

function FirstRun({ onDone }: { onDone: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await createOrg(name.trim());
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create org");
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md pt-16">
      <Card className="p-6">
        <h1 className="text-base font-semibold text-ink">
          Create your organization
        </h1>
        <p className="mt-1 mb-4 text-sm text-muted">
          You&apos;re not in any organization yet. Create one to get started —
          you&apos;ll be its admin.
        </p>
        {error && (
          <div className="mb-3">
            <ErrorBanner message={error} />
          </div>
        )}
        <form onSubmit={submit} className="flex gap-2">
          <Input
            placeholder="Organization name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
          />
          <Button type="submit" disabled={busy || !name.trim()}>
            Create
          </Button>
        </form>
      </Card>
    </div>
  );
}
