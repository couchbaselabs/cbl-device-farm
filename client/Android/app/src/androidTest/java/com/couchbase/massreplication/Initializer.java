package com.couchbase.massreplication;

import android.content.Context;

import com.couchbase.lite.CouchbaseLite;

import java.util.concurrent.atomic.AtomicBoolean;

public final class Initializer {
    private static final Initializer sInstance = new Initializer();

    private AtomicBoolean _initialized = new AtomicBoolean(false);

    private Initializer() {}

    public static Initializer getInstance() {
        return sInstance;
    }

    public void init(Context context) {
        if(!_initialized.getAndSet(true)) {
            CouchbaseLite.init(context);
        }
    }
}
