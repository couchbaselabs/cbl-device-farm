//
//  MassReplicationTests.m
//  MassReplicationTests
//
//  Created by Jim Borden on 5/14/20.
//  Copyright © 2020 Couchbase. All rights reserved.
//

#import <XCTest/XCTest.h>
#import <CouchbaseLite/CouchbaseLite.h>
#import "DFStatusAwaiter.h"

@interface MassReplicationTests : XCTestCase

@end

@implementation MassReplicationTests
{
    CBLReplicator* _replicator;
    CBLDatabase* _database;
    BOOL _setupFailed;
    DFStatusAwaiter* _replAwaiter;
}

- (void)setUp {
    NSError* error = nil;
    if(!_replicator) {
        _database = [[CBLDatabase alloc] initWithName:@"device-farm" error:&error];
        if(!_database) {
            return;
        }
        
        NSURL* addressUrl = [NSURL URLWithString:@"https://cbmobile-bucket.s3.amazonaws.com/device-farm/device_farm_sg_address.txt"];
        NSString* address = [NSString stringWithContentsOfURL:addressUrl encoding:NSASCIIStringEncoding error:&error];
        if(!address) {
            return;
        }
        
        NSURL* fullAddress = [NSURL URLWithString:[NSString stringWithFormat:@"ws://%@:4984/db/", address]];
        CBLReplicatorConfiguration* replConfig = [[CBLReplicatorConfiguration alloc] initWithDatabase:_database target:[[CBLURLEndpoint alloc] initWithURL:fullAddress]];
        replConfig.continuous = YES;
        _replicator = [[CBLReplicator alloc] initWithConfig:replConfig];
        _replAwaiter = [[DFStatusAwaiter alloc] initWithReplicator:_replicator];
    }
}

- (void)tearDown {
    [_replicator stop];
}

- (void)testAdd100Documents {
    for(NSInteger i = 1; i < 100; i++) {
        CBLMutableDocument* doc = [[CBLMutableDocument alloc] initWithID:[NSString stringWithFormat:@"doc%ld", (long)i]];
        [doc setDate:[NSDate date] forKey:@"created"];
        [doc setInteger:i forKey:@"id"];
        XCTAssertTrue([_database saveDocument:doc error:nil], @"Failed to save document");
    }
    
    [_replicator start];
    XCTAssertTrue([_replAwaiter waitForStatus:kCBLReplicatorIdle timeout:20.0]);
    XCTAssertNil(_replicator.status.error, "Replicator got error");
}

@end
