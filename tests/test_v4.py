import sys, json
sys.path.insert(0, '.')

# Full multi-trade fixture — simulates scope_filter="All activities"
fixture = {
    'executive_summary': {
        'project_health': 'Red',
        'selected_activities': 142,
        'added_activities': 18,
        'behind_schedule_count': 7,
        'ahead_of_schedule_count': 4,
        'critical_count': 5,
        'point_of_no_return_count': 4,
        'recommended_action': 'Immediate escalation required for EL - INSTALLATIONER UNDER GULVE-2.',
        'trade_counts': {'EL': 63, 'VVS': 40, 'VENT': 20, 'ARK': 30, 'BYGH': 5, 'ALL': 499}
    },
    'changed_activities': {
        'added': [
            'EL - Foringsveje-4', 'EL - INSTALLATIONER UNDER GULVE-3-1', 'EL - INSTALLATIONER UNDER GULVE-4',
            'EL - Foringsveje-5', 'EL - Belysning-4',
            'VVS - Brugsvandsinstallation-3', 'VVS - Gulvvarme etape 2',
            'VENT - Ventilationsanlæg-2', 'VENT - Kanalinstallation-3',
            'ARK - Facadebeklædning-2', 'ARK - Vinduer etape 3',
            'BYGH - Fagtilsyn uge 42', 'BYGH - Byggemøde etape 4',
        ],
        'removed': [
            'EL - LODRET FORING I SKAKT', 'EL - LODRET FORING I SKAKT-2', 'EL - SOLCELLER',
            'VVS - Faldstammer-1',
            'VENT - Udsugning-1',
        ],
        'changes': [
            {'activity': 'EL - Foringsveje-4',                  'change_type': 'Start Date', 'old': '01-10-2025', 'new': '15-10-2025'},
            {'activity': 'EL - Hovedledninger/stikledninger-4', 'change_type': 'Duration',   'old': '45 days',    'new': '60 days'},
            {'activity': 'VVS - Brugsvandsinstallation-2',      'change_type': 'Finish Date','old': '01-03-2026', 'new': '15-03-2026'},
            {'activity': 'VVS - Gulvvarme etape 1',             'change_type': 'Duration',   'old': '30 days',    'new': '45 days'},
            {'activity': 'VENT - Ventilationsanlæg-1',          'change_type': 'Start Date', 'old': '15-09-2025', 'new': '01-10-2025'},
            {'activity': 'ARK - Murerarbejde-2',                'change_type': 'Finish Date','old': '01-12-2025', 'new': '20-12-2025'},
        ]
    },
    'not_started_overdue': [],
    'progress_vs_expected': [
        # EL
        {'activity': 'EL - INSTALLATIONER UNDER GULVE-2',      'actual_pct': 30,  'expected_pct': 100, 'variance_pct': -70, 'status': 'behind'},
        {'activity': 'EL - Foringsveje-4',                      'actual_pct': 79,  'expected_pct': 97,  'variance_pct': -18, 'status': 'behind'},
        {'activity': 'EL - Hovedledninger/stikledninger-4',     'actual_pct': 26,  'expected_pct': 38,  'variance_pct': -12, 'status': 'behind'},
        {'activity': 'EL - Tavler',                             'actual_pct': 67,  'expected_pct': 45,  'variance_pct': 22,  'status': 'ahead'},
        {'activity': 'EL - Svagstrom',                          'actual_pct': 41,  'expected_pct': 30,  'variance_pct': 11,  'status': 'ahead'},
        # VVS
        {'activity': 'VVS - Brugsvandsinstallation-2',          'actual_pct': 45,  'expected_pct': 80,  'variance_pct': -35, 'status': 'behind'},
        {'activity': 'VVS - Gulvvarme etape 1',                 'actual_pct': 20,  'expected_pct': 55,  'variance_pct': -35, 'status': 'behind'},
        {'activity': 'VVS - Faldstammer-2',                     'actual_pct': 90,  'expected_pct': 75,  'variance_pct': 15,  'status': 'ahead'},
        {'activity': 'VVS - Afloeb terrændæk',                  'actual_pct': 60,  'expected_pct': 65,  'variance_pct': -5,  'status': 'behind'},
        # VENT
        {'activity': 'VENT - Ventilationsanlæg-1',              'actual_pct': 35,  'expected_pct': 70,  'variance_pct': -35, 'status': 'behind'},
        {'activity': 'VENT - Kanalinstallation-2',              'actual_pct': 55,  'expected_pct': 40,  'variance_pct': 15,  'status': 'ahead'},
        # ARK
        {'activity': 'ARK - Murerarbejde-2',                    'actual_pct': 72,  'expected_pct': 90,  'variance_pct': -18, 'status': 'behind'},
        {'activity': 'ARK - Facadebeklædning-1',                'actual_pct': 85,  'expected_pct': 70,  'variance_pct': 15,  'status': 'ahead'},
        # BYGH
        {'activity': 'BYGH - Byggemøde etape 3',                'actual_pct': 100, 'expected_pct': 100, 'variance_pct': 0,   'status': 'ahead'},
    ],
    'stage_mismatch': [
        {'activity': 'EL - INSTALLATIONER UNDER GULVE-2',  'actual_pct': 30, 'expected_pct': 100, 'difference_pct': -70, 'status': 'Critical Mismatch'},
        {'activity': 'VVS - Brugsvandsinstallation-2',     'actual_pct': 45, 'expected_pct': 80,  'difference_pct': -35, 'status': 'Mismatch'},
        {'activity': 'VENT - Ventilationsanlæg-1',         'actual_pct': 35, 'expected_pct': 70,  'difference_pct': -35, 'status': 'Mismatch'},
    ],
    'point_of_no_return': [
        {'activity': 'EL - INSTALLATIONER UNDER GULVE-2',  'actual_pct': 30, 'expected_pct': 100, 'variance_pct': -70, 'remaining_time': '-16 days', 'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'Immediate escalation and recovery plan required.'},
        {'activity': 'EL - Foringsveje-4',                 'actual_pct': 79, 'expected_pct': 97,  'variance_pct': -18, 'remaining_time': '67 days',   'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'Deploy additional resources and monitor daily progress.'},
        {'activity': 'VVS - Brugsvandsinstallation-2',     'actual_pct': 45, 'expected_pct': 80,  'variance_pct': -35, 'remaining_time': '22 days',   'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'Increase plumbing crew immediately.'},
        {'activity': 'VENT - Ventilationsanlæg-1',         'actual_pct': 35, 'expected_pct': 70,  'variance_pct': -35, 'remaining_time': '30 days',   'classification': 'Yellow', 'assessment': 'HIGH RISK',          'recommendation': 'Reassign VENT resources from completed tasks.'},
    ],
    'action_recommendations': [
        {'activity': 'EL - INSTALLATIONER UNDER GULVE-2', 'issue': 'Critical mismatch: 70% behind expected progress, point of no return.',    'actions': ['Immediate root cause analysis', 'Mobilize emergency task force', 'Reschedule dependent activities', 'Notify stakeholders', 'Prepare recovery plan']},
        {'activity': 'VVS - Brugsvandsinstallation-2',    'issue': '35% behind schedule. Insufficient plumbing crew for current stage.',       'actions': ['Increase crew size', 'Review material supply chain', 'Daily progress tracking', 'Escalate to project management']},
        {'activity': 'VENT - Ventilationsanlæg-1',        'issue': '35% behind expected. Delayed start impacting downstream duct installation.','actions': ['Reassign resources', 'Compress duct schedule', 'Weekly milestone tracking']},
        {'activity': 'EL - Foringsveje-4',                'issue': '18% behind schedule, risk of further slippage.',                           'actions': ['Assign overtime shifts', 'Reallocate skilled electricians', 'Daily progress tracking', 'Escalate to project management']},
        {'activity': 'ARK - Murerarbejde-2',              'issue': '18% behind schedule. Facade work delayed by material delivery.',            'actions': ['Chase material delivery', 'Add second masonry crew', 'Review finish date']},
    ]
}

# REMOVED: /v4/compare endpoint and format_compare_v4_as_html deleted in route cleanup
print('SKIPPED: /v4/compare formatter was removed during route cleanup.')
