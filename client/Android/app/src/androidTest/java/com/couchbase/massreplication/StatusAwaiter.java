package com.couchbase.massreplication;

import com.couchbase.lite.ListenerToken;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorChange;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class StatusAwaiter {
    private final Replicator _replicator;
    private final BlockingQueue<Replicator.ActivityLevel> _statusHistory = new LinkedBlockingQueue<>();
    private final ListenerToken _token;
    private final Executor _callbackExecutor = Executors.newSingleThreadExecutor();

    public StatusAwaiter(Replicator repl)
    {
        _replicator = repl;
        _token = _replicator.addChangeListener(_callbackExecutor, (ReplicatorChange change) -> {
            _statusHistory.add(change.getStatus().getActivityLevel());
        });
    }

    public boolean waitForStatus(Replicator.ActivityLevel status, long seconds) {
        try {
            Replicator.ActivityLevel next;
            do {
                next =_statusHistory.poll(seconds, TimeUnit.SECONDS);
                if (next == status) {
                    return true;
                }
            } while(next != null);

            return false;
        } catch (InterruptedException e) {
            return false;
        }
    }
}
