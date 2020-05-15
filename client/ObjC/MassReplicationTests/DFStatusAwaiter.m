//
//  DFStatusAwaiter.m
//  MassReplicationTests
//
//  Created by Jim Borden on 5/14/20.
//  Copyright © 2020 Couchbase. All rights reserved.
//

#import "DFStatusAwaiter.h"

@implementation DFStatusAwaiter
{
    CBLReplicator* _replicator;
    NSMutableArray* _statusHistory;
    id<CBLListenerToken> _token;
    NSCondition* _waitCondition;
    dispatch_queue_t _callbackQueue;
}

- (instancetype)initWithReplicator:(CBLReplicator * _Nonnull)replicator {
    self = [super init];
    if(self) {
        _replicator = replicator;
        _statusHistory = [NSMutableArray new];
        _waitCondition = [NSCondition new];
        _callbackQueue = dispatch_queue_create("StatusAwaiter", nil);
        __weak DFStatusAwaiter* weakSelf = self;
        _token = [_replicator addChangeListenerWithQueue:_callbackQueue listener:^(CBLReplicatorChange * _Nonnull change) {
            DFStatusAwaiter* strongSelf = weakSelf;
            if(!strongSelf) {
                return;
            }
            
            [strongSelf->_statusHistory addObject:@(change.status.activity)];
            [strongSelf->_waitCondition signal];
        }];
    }
    
    return self;
}

- (void)dealloc {
    [_replicator removeChangeListenerWithToken:_token];
}

- (BOOL)waitForStatus:(CBLReplicatorActivityLevel)level timeout:(NSTimeInterval)timeout {
    NSDate* timeLimit = [NSDate dateWithTimeInterval:timeout sinceDate:[NSDate date]];
    while(![_statusHistory containsObject:@(level)]) {
        if(![_waitCondition waitUntilDate:timeLimit]) {
            return NO;
        }
    }
    
    [_statusHistory removeAllObjects];
    return YES;
}

@end
