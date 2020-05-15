package com.couchbase.massreplication;

import android.content.Context;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;

import com.couchbase.lite.AbstractReplicator;
import com.couchbase.lite.CouchbaseLite;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorConfiguration;
import com.couchbase.lite.URLEndpoint;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.util.Date;

import okhttp3.Call;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

import static org.junit.Assert.*;

/**
 * Instrumented test, which will execute on an Android device.
 *
 * @see <a href="http://d.android.com/tools/testing">Testing documentation</a>
 */
@RunWith(AndroidJUnit4.class)
public class MassReplicationTest {
    private Replicator _replicator;
    private Database _database;
    private StatusAwaiter _replAwaiter;

    @Before
    public void setUp() throws CouchbaseLiteException, IOException, URISyntaxException {
        Initializer.getInstance().init(InstrumentationRegistry.getInstrumentation().getTargetContext());

        try {
            if (_replicator == null) {
                _database = new Database("device-farm");
                URL addressUrl = new URL("https://cbmobile-bucket.s3.amazonaws.com/device-farm/device_farm_sg_address.txt");
                OkHttpClient client = new OkHttpClient();
                Request request = new Request.Builder()
                        .url(addressUrl)
                        .build();
                Call call = client.newCall(request);
                Response response = call.execute();
                String address = response.body().string();
                URI fullAddress = new URI("ws", null, address, 4984, "/db", null, null);
                ReplicatorConfiguration replConfig = new ReplicatorConfiguration(_database, new URLEndpoint(fullAddress))
                        .setContinuous(true);
                _replicator = new Replicator(replConfig);
                _replAwaiter = new StatusAwaiter(_replicator);
            }
        } catch(Exception e) {
            e.printStackTrace();
            throw e;
        }
    }

    @After
    public void tearDown() {
        _replicator.stop();
    }

    @Test
    public void testAdd100Documents() throws CouchbaseLiteException {
        for(int i = 1; i < 100; i++) {
            MutableDocument doc = new MutableDocument(String.format("doc%d", i));
            doc.setDate("created", new Date());
            doc.setLong("id", i);
            _database.save(doc);
        }

        _replicator.start();
        assertTrue(_replAwaiter.waitForStatus(AbstractReplicator.ActivityLevel.IDLE, 20));
        assertNull(_replicator.getStatus().getError());
    }
}
