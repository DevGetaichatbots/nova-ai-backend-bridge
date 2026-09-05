import sys, json
sys.path.insert(0, '.')

# ── Comprehensive demo fixture ──────────────────────────────────────────────
# Simulates a large multi-trade hospital construction project (Rigshospitalet
# extension). Covers all 4 filter dimensions, critical path, delay drivers,
# schedule changes, PONR split, and action recommendations.

fixture = {
    'executive_summary': {
        'project_health': 'Red',
        'selected_activities': 214,
        'added_activities': 21,
        'behind_schedule_count': 11,
        'ahead_of_schedule_count': 7,
        'critical_count': 8,
        'point_of_no_return_count': 5,
        'critical_path_count': 7,
        'overall_progress_pct': 54.2,
        'recommended_action': 'Mobilise emergency crew for EL - Forsyningstavle Stuen – Building A.',
        'trade_counts': {'EL': 72, 'VVS': 51, 'VENT': 34, 'ARK': 38, 'BYGH': 19, 'ALL': 214},
    },
    'summary_notes': {
        'overall_progress_old_pct': 49.1,
        'overall_progress_new_pct': 54.2,
        'overall_progress_delta': 5.1,
        'finished_activities': 18,
        'delayed_activities': 11,
        'total_activities': 214,
        'added_count': 21,
        'removed_count': 6,
        'reporting_period_old': '2025-08-15',
        'reporting_period_new': '2025-10-01',
    },
    'filter_options': {
        'areas':  ['Building A', 'Building B', 'Building C', 'Outdoor / Site'],
        'floors': ['Basement', 'Ground Floor', '1st Floor', '2nd Floor', '3rd Floor', 'Roof'],
        'phases': ['Phase 1 – Demolition', 'Phase 2 – Structure', 'Phase 3 – MEP Rough-in', 'Phase 4 – Fit-out'],
    },

    # ── Schedule changes ────────────────────────────────────────────────────
    'changed_activities': {
        'added': [
            'EL - Nødbelysning Trapper – Building A',
            'EL - UPS-anlæg Serverrum',
            'EL - Solcelleanlæg Tag – Building B',
            'EL - Jordledninger – Outdoor',
            'VVS - Sprinkleranlæg 3. sal – Building A',
            'VVS - Køleanlæg Serverrum',
            'VVS - Regnvandshåndtering – Outdoor',
            'VENT - Brandsikring Ventilation – Building C',
            'VENT - Tryksætning Trapper – Building A',
            'ARK - Indvendig glasfacade – Building B 2. sal',
            'ARK - Akustikloft 1. sal – Building C',
            'ARK - Elevator lobby – Building A Stuen',
            'BYGH - Byggepladsindretning etape 3',
            'BYGH - Geopil-kontrol – Outdoor',
            'BYGH - Afleveringsgennemgang etape 1',
            'BYGH - Byggemøde uge 42',
            'BYGH - Byggemøde uge 46',
            'EL - Potentialudligning Kælder – Building A',
            'VVS - Afspærringshaner etage 2 – Building B',
            'ARK - Fugearbejde facader – Building C',
            'VENT - Serviceluger Teknikrum',
        ],
        'removed': [
            'EL - LODRET FORING I SKAKT Blok 1',
            'EL - Midlertidig tavle fase 1',
            'VVS - Faldstammer etape 1 – Building A',
            'VENT - Udsugning Kælder – Building B',
            'ARK - Midlertidigt hegn nord',
            'BYGH - Byggemøde uge 34',
        ],
        'changes': [
            {'activity': 'EL - Forsyningstavle Stuen – Building A',        'change_type': 'Finish Date', 'old': '01-09-2025', 'new': '01-11-2025'},
            {'activity': 'EL - Kabelinstallation 1. sal – Building A',     'change_type': 'Duration',    'old': '30 days',    'new': '48 days'},
            {'activity': 'EL - Kabelinstallation 2. sal – Building B',     'change_type': 'Start Date',  'old': '15-08-2025', 'new': '01-09-2025'},
            {'activity': 'VVS - Brugsvandsinstallation 2. sal – Building A','change_type': 'Finish Date','old': '15-10-2025', 'new': '01-12-2025'},
            {'activity': 'VVS - Gulvvarme Stuen – Building B',             'change_type': 'Duration',    'old': '21 days',    'new': '35 days'},
            {'activity': 'VVS - Afløbsinstallation Kælder – Building A',   'change_type': 'Start Date',  'old': '01-07-2025', 'new': '15-07-2025'},
            {'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',    'change_type': 'Finish Date', 'old': '01-10-2025', 'new': '15-11-2025'},
            {'activity': 'VENT - Kanalinstallation Kælder – Building B',   'change_type': 'Duration',    'old': '14 days',    'new': '25 days'},
            {'activity': 'ARK - Murerarbejde Facade – Building C',         'change_type': 'Finish Date', 'old': '01-11-2025', 'new': '20-12-2025'},
            {'activity': 'ARK - Terrazzogulv 1. sal – Building A',         'change_type': 'Duration',    'old': '18 days',    'new': '28 days'},
            {'activity': 'BYGH - Betonstøbning Dæk 2 – Building B',        'change_type': 'Start Date',  'old': '01-08-2025', 'new': '20-08-2025'},
            {'activity': 'BYGH - Pæleramning – Outdoor',                   'change_type': 'Finish Date', 'old': '15-07-2025', 'new': '01-08-2025'},
        ],
    },

    # ── Progress vs expected ─────────────────────────────────────────────────
    'progress_vs_expected': [
        # EL — Building A
        {'activity': 'EL - Forsyningstavle Stuen – Building A',        'actual_pct': 22,  'expected_pct': 100, 'variance_pct': -78, 'status': 'behind', 'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'EL - Kabelinstallation 1. sal – Building A',     'actual_pct': 55,  'expected_pct': 85,  'variance_pct': -30, 'status': 'behind', 'location': {'floor': '1st Floor',    'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'EL - Belysning Kælder – Building A',             'actual_pct': 88,  'expected_pct': 70,  'variance_pct': 18,  'status': 'ahead',  'location': {'floor': 'Basement',     'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'EL - Potentialudligning Kælder – Building A',    'actual_pct': 100, 'expected_pct': 100, 'variance_pct': 0,   'status': 'ahead',  'location': {'floor': 'Basement',     'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        # EL — Building B
        {'activity': 'EL - Kabelinstallation 2. sal – Building B',     'actual_pct': 38,  'expected_pct': 60,  'variance_pct': -22, 'status': 'behind', 'location': {'floor': '2nd Floor',    'area': 'Building B', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'EL - Tavleinstallation 3. sal – Building B',     'actual_pct': 72,  'expected_pct': 55,  'variance_pct': 17,  'status': 'ahead',  'location': {'floor': '3rd Floor',    'area': 'Building B', 'phase': 'Phase 4 – Fit-out'}},
        # EL — Building C
        {'activity': 'EL - Jordledninger Teknikrum – Building C',      'actual_pct': 15,  'expected_pct': 50,  'variance_pct': -35, 'status': 'behind', 'location': {'floor': 'Basement',     'area': 'Building C', 'phase': 'Phase 2 – Structure'}},
        {'activity': 'EL - Svagstromsinstallation – Building C',       'actual_pct': 63,  'expected_pct': 45,  'variance_pct': 18,  'status': 'ahead',  'location': {'floor': '1st Floor',    'area': 'Building C', 'phase': 'Phase 3 – MEP Rough-in'}},
        # VVS — Building A
        {'activity': 'VVS - Brugsvandsinstallation 2. sal – Building A','actual_pct': 41,  'expected_pct': 80,  'variance_pct': -39, 'status': 'behind', 'location': {'floor': '2nd Floor',    'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Afløbsinstallation Kælder – Building A',   'actual_pct': 92,  'expected_pct': 80,  'variance_pct': 12,  'status': 'ahead',  'location': {'floor': 'Basement',     'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Sprinkleranlæg Stuen – Building A',        'actual_pct': 28,  'expected_pct': 65,  'variance_pct': -37, 'status': 'behind', 'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        # VVS — Building B
        {'activity': 'VVS - Gulvvarme Stuen – Building B',             'actual_pct': 19,  'expected_pct': 55,  'variance_pct': -36, 'status': 'behind', 'location': {'floor': 'Ground Floor', 'area': 'Building B', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Faldstammer 1. sal – Building B',          'actual_pct': 87,  'expected_pct': 70,  'variance_pct': 17,  'status': 'ahead',  'location': {'floor': '1st Floor',    'area': 'Building B', 'phase': 'Phase 3 – MEP Rough-in'}},
        # VENT — Building A
        {'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',    'actual_pct': 30,  'expected_pct': 75,  'variance_pct': -45, 'status': 'behind', 'location': {'floor': 'Roof',          'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VENT - Kanalinstallation 1. sal – Building A',   'actual_pct': 58,  'expected_pct': 40,  'variance_pct': 18,  'status': 'ahead',  'location': {'floor': '1st Floor',    'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        # VENT — Building B
        {'activity': 'VENT - Kanalinstallation Kælder – Building B',   'actual_pct': 34,  'expected_pct': 70,  'variance_pct': -36, 'status': 'behind', 'location': {'floor': 'Basement',     'area': 'Building B', 'phase': 'Phase 3 – MEP Rough-in'}},
        # ARK — Building A
        {'activity': 'ARK - Terrazzogulv 1. sal – Building A',         'actual_pct': 62,  'expected_pct': 90,  'variance_pct': -28, 'status': 'behind', 'location': {'floor': '1st Floor',    'area': 'Building A', 'phase': 'Phase 4 – Fit-out'}},
        {'activity': 'ARK - Gipsvægge 2. sal – Building A',            'actual_pct': 78,  'expected_pct': 60,  'variance_pct': 18,  'status': 'ahead',  'location': {'floor': '2nd Floor',    'area': 'Building A', 'phase': 'Phase 4 – Fit-out'}},
        # ARK — Building C
        {'activity': 'ARK - Murerarbejde Facade – Building C',         'actual_pct': 47,  'expected_pct': 80,  'variance_pct': -33, 'status': 'behind', 'location': {'floor': 'Ground Floor', 'area': 'Building C', 'phase': 'Phase 2 – Structure'}},
        # BYGH
        {'activity': 'BYGH - Betonstøbning Dæk 2 – Building B',        'actual_pct': 68,  'expected_pct': 90,  'variance_pct': -22, 'status': 'behind', 'location': {'floor': '2nd Floor',    'area': 'Building B', 'phase': 'Phase 2 – Structure'}},
        {'activity': 'BYGH - Pæleramning – Outdoor',                   'actual_pct': 100, 'expected_pct': 100, 'variance_pct': 0,   'status': 'ahead',  'location': {'floor': '',             'area': 'Outdoor / Site', 'phase': 'Phase 1 – Demolition'}},
    ],

    # ── Not started overdue ──────────────────────────────────────────────────
    'not_started_overdue': [
        {'activity': 'EL - Nødbelysning Trapper – Building A',   'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Køleanlæg Serverrum',                'location': {'floor': 'Basement',     'area': 'Building C', 'phase': 'Phase 4 – Fit-out'}},
        {'activity': 'VENT - Brandsikring Ventilation – Building C','location': {'floor': '1st Floor',  'area': 'Building C', 'phase': 'Phase 3 – MEP Rough-in'}},
    ],

    # ── Point of No Return ───────────────────────────────────────────────────
    'point_of_no_return': [
        {'activity': 'EL - Forsyningstavle Stuen – Building A',      'actual_pct': 22,  'expected_pct': 100, 'variance_pct': -78, 'remaining_time': '-22 days', 'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'Emergency escalation. Delay cascades to all downstream EL work in Building A.',     'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',  'actual_pct': 30,  'expected_pct': 75,  'variance_pct': -45, 'remaining_time': '-8 days',  'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'AHU delivery must be expedited immediately. Entire VENT phase blocked.',            'location': {'floor': 'Roof',         'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Brugsvandsinstallation 2. sal – Building A','actual_pct': 41,'expected_pct': 80, 'variance_pct': -39, 'remaining_time': '4 days',   'classification': 'Red',    'assessment': 'POINT OF NO RETURN', 'recommendation': 'Increase plumbing crew to 3 teams. Final chance before pressure test milestone.', 'location': {'floor': '2nd Floor',    'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'ARK - Murerarbejde Facade – Building C',       'actual_pct': 47,  'expected_pct': 80,  'variance_pct': -33, 'remaining_time': '12 days',  'classification': 'Yellow', 'assessment': 'HIGH RISK',          'recommendation': 'Add second masonry crew. Scaffold contract expires in 12 days.',                 'location': {'floor': 'Ground Floor', 'area': 'Building C', 'phase': 'Phase 2 – Structure'}},
        {'activity': 'EL - Kabelinstallation 1. sal – Building A',   'actual_pct': 55,  'expected_pct': 85,  'variance_pct': -30, 'remaining_time': '18 days',  'classification': 'Yellow', 'assessment': 'HIGH RISK',          'recommendation': 'Assign 2 additional electricians. Ceiling closure scheduled in 18 days.',       'location': {'floor': '1st Floor',    'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
    ],

    # ── Critical Path ────────────────────────────────────────────────────────
    'critical_path_activities': [
        {'activity': 'EL - Forsyningstavle Stuen – Building A',        'start_date': '01-07-2025', 'finish_date': '01-11-2025', 'actual_pct': 22,  'float_days': 0, 'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Sprinkleranlæg Stuen – Building A',        'start_date': '15-07-2025', 'finish_date': '15-10-2025', 'actual_pct': 28,  'float_days': 0, 'location': {'floor': 'Ground Floor', 'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',    'start_date': '01-08-2025', 'finish_date': '15-11-2025', 'actual_pct': 30,  'float_days': 0, 'location': {'floor': 'Roof',         'area': 'Building A', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'VVS - Gulvvarme Stuen – Building B',             'start_date': '01-08-2025', 'finish_date': '05-11-2025', 'actual_pct': 19,  'float_days': 0, 'location': {'floor': 'Ground Floor', 'area': 'Building B', 'phase': 'Phase 3 – MEP Rough-in'}},
        {'activity': 'ARK - Terrazzogulv 1. sal – Building A',         'start_date': '15-09-2025', 'finish_date': '12-12-2025', 'actual_pct': 62,  'float_days': 0, 'location': {'floor': '1st Floor',    'area': 'Building A', 'phase': 'Phase 4 – Fit-out'}},
        {'activity': 'BYGH - Betonstøbning Dæk 2 – Building B',        'start_date': '20-08-2025', 'finish_date': '30-10-2025', 'actual_pct': 68,  'float_days': 0, 'location': {'floor': '2nd Floor',    'area': 'Building B', 'phase': 'Phase 2 – Structure'}},
        {'activity': 'ARK - Murerarbejde Facade – Building C',         'start_date': '01-09-2025', 'finish_date': '20-12-2025', 'actual_pct': 47,  'float_days': 0, 'location': {'floor': 'Ground Floor', 'area': 'Building C', 'phase': 'Phase 2 – Structure'}},
    ],

    # ── Delay Drivers ────────────────────────────────────────────────────────
    'delay_drivers': [
        {
            'driver': 'Labour shortage — EL & VENT trades',
            'description': 'Insufficient certified electricians and VENT fitters on site during weeks 36–41. Peak concurrent demand across Building A and B exceeded available subcontractor capacity by ~40%.',
            'affected_count': 7,
        },
        {
            'driver': 'Material delivery delay — VVS supply chain',
            'description': 'Sprinkler heads and copper fittings held at customs for 3 weeks due to documentation error. Plumbing rough-in across Ground Floor cannot proceed until materials are on site.',
            'affected_count': 5,
        },
        {
            'driver': 'Scope change — AHU-1 redesign (VENT)',
            'description': 'AHU-1 unit specification revised after coordination model clash detected in week 38. New unit requires extended lead time of 6 weeks. Entire ventilation rough-in in Building A blocked.',
            'affected_count': 4,
        },
        {
            'driver': 'Late structural handover — Building C',
            'description': 'Concrete drying on 2nd floor slab took 9 days longer than planned due to wet weather in September. MEP trades could not start until structural sign-off was issued.',
            'affected_count': 3,
        },
        {
            'driver': 'Coordination clash — EL vs ARK ceiling void',
            'description': 'Cable tray routes on 1st floor conflict with ARK ceiling void dimensions. Requires RFI resolution before EL can continue. RFI submitted week 40, response pending.',
            'affected_count': 2,
        },
    ],

    # ── Stage mismatch ───────────────────────────────────────────────────────
    'stage_mismatch': [
        {'activity': 'EL - Forsyningstavle Stuen – Building A',      'actual_pct': 22,  'expected_pct': 100, 'difference_pct': -78, 'status': 'Critical Mismatch'},
        {'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',  'actual_pct': 30,  'expected_pct': 75,  'difference_pct': -45, 'status': 'Critical Mismatch'},
        {'activity': 'VVS - Sprinkleranlæg Stuen – Building A',      'actual_pct': 28,  'expected_pct': 65,  'difference_pct': -37, 'status': 'Mismatch'},
        {'activity': 'VVS - Gulvvarme Stuen – Building B',           'actual_pct': 19,  'expected_pct': 55,  'difference_pct': -36, 'status': 'Mismatch'},
        {'activity': 'VENT - Kanalinstallation Kælder – Building B', 'actual_pct': 34,  'expected_pct': 70,  'difference_pct': -36, 'status': 'Mismatch'},
    ],

    # ── Action recommendations (WSID) ────────────────────────────────────────
    'action_recommendations': [
        {
            'activity': 'EL - Forsyningstavle Stuen – Building A',
            'issue': 'CRITICAL: 78% behind expected progress. Point of no return passed. All downstream EL activities in Building A blocked.',
            'actions': [
                'Convene emergency recovery meeting with EL subcontractor today',
                'Deploy 4 additional certified electricians from reserve pool',
                'Reschedule dependent ceiling closure works in Building A',
                'Notify client and project director — delay to handover anticipated',
                'Prepare formal delay notification and updated programme',
                'Install temporary distribution board to unblock other trades',
            ],
        },
        {
            'activity': 'VENT - Ventilationsanlæg AHU-1 – Building A',
            'issue': 'CRITICAL: AHU-1 unit delayed 6 weeks. Entire ventilation rough-in blocked. Point of no return reached.',
            'actions': [
                'Expedite AHU-1 delivery — contact manufacturer for air-freight option',
                'Evaluate temporary ventilation solution for occupied areas',
                'Redirect VENT crew to Building B to maintain productivity',
                'Issue formal scope change notice for programme impact',
                'Update commissioning and testing timeline',
            ],
        },
        {
            'activity': 'VVS - Brugsvandsinstallation 2. sal – Building A',
            'issue': '39% behind schedule. 4 days until point of no return. Pressure test milestone will be missed.',
            'actions': [
                'Increase VVS crew from 1 to 3 teams immediately',
                'Extend working hours to include Saturday',
                'Confirm material stock on site for 2nd floor rough-in',
                'Daily progress check with site manager',
            ],
        },
        {
            'activity': 'VVS - Sprinkleranlæg Stuen – Building A',
            'issue': '37% behind schedule. Material delivery delay is root cause.',
            'actions': [
                'Chase customs clearance for sprinkler heads — escalate to logistics manager',
                'Identify alternative local supplier for temporary supply',
                'Update fire safety commissioning schedule',
            ],
        },
        {
            'activity': 'ARK - Murerarbejde Facade – Building C',
            'issue': '33% behind schedule. Scaffold contract expires in 12 days.',
            'actions': [
                'Negotiate scaffold contract extension (minimum 3 weeks)',
                'Deploy second masonry crew — request from ARK subcontractor',
                'Prioritise load-bearing facades before decorative elements',
            ],
        },
    ],
}


# REMOVED: /v5/compare endpoint and format_compare_v5_as_html deleted in route cleanup
print('SKIPPED: /v5/compare formatter was removed during route cleanup.')
