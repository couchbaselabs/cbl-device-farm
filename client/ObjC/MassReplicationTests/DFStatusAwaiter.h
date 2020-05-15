//
//  DFStatusAwaiter.h
//  MassReplication
//
//  Created by Jim Borden on 5/14/20.
//  Copyright © 2020 Couchbase. All rights reserved.
//

#import <Foundation/Foundation.h>
#import <CouchbaseLite/CouchbaseLite.h>

@interface DFStatusAwaiter : NSObject

- (instancetype)initWithReplicator: (CBLReplicator *)replicator;

- (BOOL)waitForStatus: (CBLReplicatorActivityLevel)level timeout: (NSTimeInterval)timeout;

@end
