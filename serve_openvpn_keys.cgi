#!/usr/bin/perl -w

use strict;
use DBI;
use CGI;
my $dbname = 'tbdb';
my $vpnd = q{128.2.208.2};
my $cacrt = q{/usr/testbed/etc/openvpn.crt};
my $oconfig = q{/usr/testbed/etc/TEST-openvpn-clients.cfg};
my $clientpath = q{/etc/openvpn}; # Where the client should untar this thing..
use Archive::Tar;

main();

###########################
# Input: wanode key
# Output: tarball with all the config stuff for that node
###########################
# Note that the database utility functions are taken from a
# public-domain project (POUND) and are thus not themselves
# candidates for exclusive copyright. Otherwise, this code
# is written by Pat Gunn as part of the Emulab project and is released under
# the same license as the rest of the emulab project.
###################################################
# By a design decision, this explicitly has permission to expose the
# entire sw_configfiles table.
###################################################

sub main
{
my $query = new CGI;

if(! -f $cacrt) {die "No CA file installed!\n"};
if(! -f $oconfig) {die "No openvpn client config template installed!\n"};

my %cfg;
$cfg{keytype} = 'wa_openvpn'; # These two are defaults - allow overrides
$cfg{conid} = 0;
$cfg{port} = 1194;
$cfg{dev} = 'tun'; # Default for homenet

if($query->param('wakey'))
	{$cfg{wakey} = $query->param('wakey');}
if($query->param('keytype'))
	{$cfg{keytype} = $query->param('keytype');}
if($query->param('conid'))
	{$cfg{conid} = $query->param('conid');}
if($query->param('nodeid'))
	{$cfg{nodeid} = $query->param('nodeid');}
if($query->param('port'))
	{$cfg{port} = $query->param('port');}
if($query->param('dev'))
	{$cfg{dev} = $query->param('dev');}

foreach my $key (keys %cfg)
	{
	$cfg{$key} =~ tr/\n\f\r'";//d; # Sanitise the inputs
	}

my $dbh = db_connect();
if(! defined $cfg{nodeid})
	{
	if(defined($cfg{wakey}))
		{$cfg{nodeid} = get_nodeid_from_key($dbh, $cfg{wakey});}
	else
		{die "Nodeid not provided, no wideareakey provided\n";}
	}

if(! defined($cfg{nodeid})) {do_error($query, "Unknown key [$cfg{wakey}]");}
my $clientconf = fix_oconfig($oconfig, \%cfg);

my $memtar = Archive::Tar->new();

print $query->header(-type => 'application/x-tar');
my $dq = $dbh->prepare("SELECT file,data FROM sw_configfiles WHERE node_id=? AND swid=? AND connection_id=?");
$dq->execute($cfg{nodeid}, $cfg{keytype}, $cfg{conid});

while(my %thisrow = get_dbresults($dq))
	{
	$memtar->add_data("$cfg{conid}/$cfg{nodeid}.$thisrow{file}", $thisrow{data});
	}

if($cfg{keytype} eq 'wa_openvpn')
	{
	$memtar->add_data("$cfg{conid}/ca.crt", slurp_file($cacrt));
	}
elsif($cfg{keytype} eq 'mv_openvpn')
	{
	my $dqc = $dbh->prepare("SELECT file,data FROM sw_configfiles WHERE connection_id=? AND swid=?");
	$dqc->execute($cfg{conid}, 'mvc_openvpn'); # Special key to hold CA certs
	while(my %thisrow = get_dbresults($dqc))
		{$memtar->add_data("$cfg{conid}/ca.crt", $thisrow{data});}

	}
else
	{die "Unknown keytype\n";}

$memtar->add_data('openvpn.conf', $clientconf);

my $tardat = $memtar->write(); # give us a string with the in-memory tarball..

print $tardat;
print STDERR "serve_openvpn_keys served node [$cfg{nodeid}] OK\n";
}

sub db_connect
{
my $dbh = DBI->connect("dbi:mysql:dbname=$dbname");
if($dbh->ping)
        {
#	if($debug) {print "Connected";}
        }
else    
	{die "Not connected: $!\n";}
return $dbh;
}

sub get_nodeid_from_key
{
my ($dbh, $wakey) = @_;

my $nq = $dbh->prepare("SELECT node_id FROM widearea_nodeinfo WHERE privkey=?");
$nq->execute($wakey);
return get_dbval($nq);
}

sub get_dbval($)
{ # Return result from a query that at most generates a single value
my ($dbq) = @_;
my $res = $dbq->fetchall_arrayref();
return $$res[0][0];
}

sub do_error
{
my ($query, $err) = @_;
print $query->header(-type => 'text/plain');
print STDERR "Failure in serve_openvpn_keys: $err\n";
die "ERROR (serve_openvpn_keys)! $err!\n";
}

sub get_dbresults($)
{ # Returns a proper hash instead of a reference to one, for FIRST record returned
my ($dbq) = @_;
my $reshdl = $dbq->fetchrow_hashref();
my %returner;
if(defined($reshdl))
	{
	%returner = %$reshdl;
	}
return %returner;
}

sub slurp_file
{
my ($fts) = @_;
open(FTS, $fts) || die "Failed to open $fts:$!\n";
local $/;
my $ret = readline(FTS);
close(FTS);
return $ret;
}

sub fix_oconfig
{
my ($ctemplate, $cfg) = @_;

my $nwk		= $$cfg{conid}; # This is numeric, and it's the vpnid
my $nodeid	= $$cfg{nodeid};
my $port	= $$cfg{port};
my $dev		= $$cfg{dev};
my $tdat = slurp_file($ctemplate);

$tdat =~ s/\$vpnd/$vpnd/g; # Replace in-file placeholder with our variable
$tdat =~ s/\$cfgpath/$clientpath/g;
$tdat =~ s/\$cfgnwk/$nwk/g; 
$tdat =~ s/\$clientname/$nodeid/g;
$tdat =~ s/\$port/$port/g;
$tdat =~ s/\$dev/$dev/g;
return $tdat;
}

