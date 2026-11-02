'use client';

import { Box, Button, Link as MuiLink, Skeleton, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useQuery } from '@tanstack/react-query';
import NextLink from 'next/link';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { buildOnTheWaterUrl, type ShippingFilterParams } from '@/app/(app)/shipping/buildShippingLinesUrl';
import { apiGet, safeDisplayError } from '@/lib/api';
import { tokensFor } from '@/theme/cipTokens';

import { BASEMAP_DOTS, BASEMAP_SIZE } from './basemapDots';
import { badgeText, daysText, fmtDay, fmtDayYear, fmtMoney, fmtUnits, historyText, nameUnits, slipShort } from './format';
import { clusterChip, clusterVessels, placeLabels, portsInUse, type Cluster } from './layout';
import type { OnTheWaterData, PortRow, Vessel } from './types';

type View = 'map' | 'distributor';

export type OnTheWaterProps = {
  /** The page scope (filters), shared with the KPI tiles and the grid. */
  filterParams: ShippingFilterParams;
  /** Key of the vessel the grid is filtered to, if any. */
  selectedKey?: string | null;
  onSelectVessel: (key: string | null) => void;
  onOpenNeedsLook: () => void;
  /** The "Arriving this week by distributor" chart: the second view. */
  byDistributor: ReactNode;
};

function useOnTheWater(filterParams: ShippingFilterParams) {
  const url = buildOnTheWaterUrl(filterParams);
  return useQuery({
    queryKey: ['shipping-on-the-water', url],
    queryFn: ({ signal }) => apiGet<OnTheWaterData>(url, { signal }),
    staleTime: 60_000,
  });
}

export function OnTheWater({ filterParams, selectedKey, onSelectVessel, onOpenNeedsLook, byDistributor }: OnTheWaterProps) {
  const theme = useTheme();
  const t = tokensFor(theme.palette.mode);
  const [view, setView] = useState<View>('map');
  const [hoverId, setHoverId] = useState<string | null>(null);
  const { data, isLoading, isError, error, refetch } = useOnTheWater(filterParams);
  // Labels are a fixed size in pixels, so their size on the map follows the map's real size (a phone is not a desk).
  const mapRef = useRef<HTMLDivElement | null>(null);
  const [mapPx, setMapPx] = useState({ w: 1000, h: 646 });
  // Phone-width map: a port nobody is sailing to or from is a dot that shows its name when tapped.
  const [tappedPort, setTappedPort] = useState<string | null>(null);
  const hasData = Boolean(data);
  useEffect(() => {
    const el = mapRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => setMapPx({ w: el.clientWidth || 1000, h: el.clientHeight || 646 });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [view, hasData]);

  const card = {
    bgcolor: t.bg.surface,
    border: `1px solid ${t.border.subtle}`,
    borderRadius: 1.5,
    p: 2,
  } as const;
  const muted = { color: t.text.secondary } as const;
  const amber = t.semantic.warning;

  if (isLoading) {
    return (
      <Box data-testid="on-the-water" sx={{ mt: 1.5 }}>
        <Skeleton variant="rounded" height={320} />
      </Box>
    );
  }
  if (isError || !data || !data.tiles || !Array.isArray(data.vessels)) {
    return (
      <Box data-testid="on-the-water" sx={{ mt: 1.5, ...card }}>
        <Typography variant="body2" color="error">
          On the water could not be loaded{error ? `: ${safeDisplayError(error)}` : ''}.{' '}
          <Button size="small" onClick={() => void refetch()}>
            Retry
          </Button>
        </Typography>
        <Box sx={{ mt: 1 }}>{byDistributor}</Box>
      </Box>
    );
  }

  const noVessels = data.vessels.length === 0;
  const picked = data.vessels.find((v) => v.key === selectedKey) ?? null;
  const panel = picked ?? data.vessels[0] ?? null;
  const reportLine = [
    'ACZA Shipped / Unshipped',
    data.report_date ? `report of ${fmtDayYear(data.report_date)}` : null,
    data.reports.earlier > 0 ? `compared with ${data.reports.earlier} earlier ${data.reports.earlier === 1 ? 'report' : 'reports'}${data.reports.since ? ` since ${fmtDay(data.reports.since)}` : ''}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const air = data.tiles.at_sea.air_units;
  const moved = data.tiles.eta_moved;
  const tiles: Array<{ key: string; label: string; value: string; unit: string; sub: ReactNode; warn?: boolean }> = [
    {
      key: 'at-sea',
      label: 'At sea',
      value: fmtUnits(data.tiles.at_sea.units),
      unit: 'units',
      sub: (
        <>
          {[fmtMoney(data.tiles.at_sea.amount), `${data.tiles.at_sea.vessels} ${data.tiles.at_sea.vessels === 1 ? 'vessel' : 'vessels'}`, `${fmtUnits(data.tiles.at_sea.lines)} lines`].join(' · ')}
          {air > 0 ? <Box component="span" sx={{ display: 'block' }}>{`+${fmtUnits(air)} units by air`}</Box> : null}
        </>
      ),
    },
    {
      key: 'arrived',
      label: 'Arrived, not yet delivered',
      value: fmtUnits(data.tiles.arrived.units),
      unit: 'units',
      sub: data.tiles.arrived.by_port.length ? data.tiles.arrived.by_port.map((p) => `${p.name} ${fmtUnits(p.units)}`).join(' · ') : 'Nothing waiting at a port',
    },
    {
      key: 'booked',
      label: 'Booked, not on board yet',
      value: fmtUnits(data.tiles.booked.units),
      unit: 'units',
      sub: `${fmtUnits(data.tiles.booked.lines)} lines with a future on-board date`,
    },
    {
      key: 'eta-moved',
      label: moved.since ? `ETA moved since ${fmtDay(moved.since)}` : 'ETA moved',
      value: `${moved.vessels_moved} of ${moved.vessels}`,
      unit: 'vessels',
      sub: moved.vessels_moved > 0 ? `Later by ${moved.min_days === moved.max_days ? moved.min_days : `${moved.min_days} to ${moved.max_days}`} days · from report history` : 'No ETA has moved · from report history',
      warn: moved.vessels_moved > 0,
    },
  ];

  const clusters = clusterVessels(data.vessels, data.map.cluster_radius_pct);
  const hoverCluster = clusters.find((c) => c.vessels.some((v) => v.id === hoverId)) ?? null;
  const hoverVessel = hoverCluster?.vessels.find((v) => v.id === hoverId) ?? null;
  const durban = data.map.ports.find((p) => p.id === 'DURBAN');
  const labelTargets = [
    ...clusters.filter((c) => c.vessels.length > 1).map((c) => ({ id: `c:${c.id}`, x: c.x, y: c.y, priority: c.vessels.some((v) => v.id === panel?.id) ? 0 : 1 })),
    ...clusters.filter((c) => c.vessels.length === 1).map((c) => ({ id: c.vessels[0].id, x: c.x, y: c.y, priority: c.vessels[0].id === panel?.id ? 0 : 2 })),
  ];
  const pctX = (px: number) => (px / mapPx.w) * 100;
  const pctY = (px: number) => (px / mapPx.h) * 100;
  const narrow = mapPx.w < 560;
  const compactPorts = mapPx.w < 600;
  const namedPorts = compactPorts ? portsInUse(data.vessels, data.map.ports) : null;
  const portNamed = (id: string) => namedPorts === null || namedPorts.has(id) || tappedPort === id;
  // Port names and vessel markers are not to be covered by a label.
  const avoid = [
    ...data.map.ports
      .filter((p) => portNamed(p.id))
      .map((p) => {
        const w = pctX(p.label.length * 7.6 + 12);
        const side = p.label_side ?? (p.x > 82 ? 'left' : 'right');
        if (side === 'above') return { id: `p:${p.id}`, x: p.x - w / 2, y: p.y - pctY(26), w, h: pctY(18) };
        return { id: `p:${p.id}`, x: side === 'left' ? p.x - pctX(6) - w : p.x + pctX(6), y: p.y - pctY(9), w, h: pctY(18) };
      }),
    ...clusters.map((c) => ({ id: `m:${c.id}`, x: c.x - pctX(14), y: c.y - pctY(14), w: pctX(28), h: pctY(28) })),
    // The Durban note sits on the map (not under it) except on a phone-width map.
    ...(durban && !narrow
      ? [{ id: 'durban-note', x: Math.min(durban.x + 5.4, 62), y: Math.min(durban.y + 4.3, 94), w: pctX(260), h: pctY(34) }]
      : []),
  ];
  // The selected vessel and up to four others; a phone-width map labels the selected one only.
  const placed = placeLabels(labelTargets, { w: pctX(narrow ? 128 : 160), h: pctY(42) }, avoid, { x: pctX(16), y: pctY(10) }).slice(0, narrow ? 1 : 5);
  const labelOf = new Map(placed.map((b) => [b.id, b]));
  const durbanRow = data.port_rows.find((r) => r.code === 'ZADUR');


  const MapNotes = () => (
    <>
      {durban ? (
        <Box
          sx={{
            ...(narrow ? { display: 'inline-block' } : { position: 'absolute', left: `${Math.min(durban.x + 5.4, 62)}%`, top: `${Math.min(durban.y + 4.3, 94)}%` }),
            px: 1.25, py: 0.75, borderRadius: 1, bgcolor: alpha(t.bg.default, 0.88), border: `1px solid ${alpha(amber, 0.55)}`, fontSize: 11, color: amber, whiteSpace: 'nowrap',
          }}
          data-testid="otw-durban-note"
        >
          Durban · {conditionText(durbanRow)}
        </Box>
      ) : null}
      <Typography variant="caption" sx={{ ...(narrow ? { display: 'block' } : { position: 'absolute', left: 12, bottom: 8 }), color: t.text.muted, fontSize: 11 }}>
        As of {fmtDayYear(data.as_of)} · position = share of on-board → ETA elapsed, along the usual lane
      </Typography>
    </>
  );

  return (
    <Box data-testid="on-the-water" sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <Box>
          <Typography component="h2" variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            On the water
          </Typography>
          <Typography variant="body2" sx={muted}>
            {reportLine}
          </Typography>
          <Typography variant="caption" sx={muted} data-testid="otw-data-as-of">
            Data as of {data.report_date ? fmtDayYear(data.report_date) : 'no report yet'}
            {data.report_stale ? (
              <Box component="span" sx={{ ml: 1, color: amber, fontWeight: 600 }} data-testid="otw-stale">
                Report is {data.report_age_days} days old
              </Box>
            ) : null}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.25, alignItems: 'center' }}>
          <Box
            component="span"
            sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, px: 1.5, py: 0.75, borderRadius: 999, border: `1px solid ${alpha(amber, 0.5)}`, color: amber, fontSize: 12, fontWeight: 600 }}
          >
            <Box component="span" sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: amber }} />
            Positions estimated · live tracking Planned
          </Box>
          <Box role="group" aria-label="View" sx={{ display: 'inline-flex', border: `1px solid ${t.border.strong}`, borderRadius: 1.25, overflow: 'hidden' }}>
            {(['map', 'distributor'] as const).map((v, i) => (
              <Box
                key={v}
                component="button"
                type="button"
                aria-pressed={view === v}
                onClick={() => setView(v)}
                sx={{
                  minHeight: 36, px: 1.75, border: 0, borderLeft: i ? `1px solid ${t.border.strong}` : 0, cursor: 'pointer', font: 'inherit', fontSize: 13,
                  fontWeight: view === v ? 600 : 400, bgcolor: view === v ? t.accent.primaryMuted : 'transparent', color: view === v ? t.accent.primary : t.text.secondary,
                }}
              >
                {v === 'map' ? 'Map' : 'By distributor'}
              </Box>
            ))}
          </Box>
        </Box>
      </Box>

      {view === 'distributor' ? (
        <Box sx={card}>{byDistributor}</Box>
      ) : (
        <>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 1.5 }}>
            {tiles.map((x) => (
              <Box key={x.key} data-testid={`otw-tile-${x.key}`} sx={{ ...card, borderColor: x.warn ? alpha(amber, 0.45) : t.border.subtle, display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                <Typography variant="caption" sx={{ color: x.warn ? amber : t.text.secondary, fontSize: 12 }}>
                  {x.label}
                </Typography>
                <Typography component="div" sx={{ fontSize: 26, fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1.15 }}>
                  {x.value}{' '}
                  <Box component="span" sx={{ fontSize: 14, fontWeight: 500, color: t.text.secondary }}>
                    {x.unit}
                  </Box>
                </Typography>
                <Typography variant="caption" sx={{ color: t.text.secondary, fontSize: 12 }}>
                  {x.sub}
                </Typography>
              </Box>
            ))}
          </Box>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'stretch' }}>
            <Box
              sx={{
                flex: '999 1 600px', minWidth: 0, ...card, p: 1.75, display: 'flex', flexDirection: 'column', gap: 1.25,
                background: theme.palette.mode === 'dark' ? 'radial-gradient(ellipse at 60% 55%, #18222c 0%, #121519 70%)' : 'radial-gradient(ellipse at 60% 55%, #e6eef3 0%, #f6f9fb 70%)',
              }}
            >
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.75, alignItems: 'center', justifyContent: 'space-between', px: 0.5 }}>
                <Typography sx={{ fontSize: 14, fontWeight: 600 }}>Vessels and lanes</Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.75, fontSize: 12, color: t.text.secondary }}>
                  <Legend swatch={<Box sx={{ width: 18, borderTop: `2px dotted ${t.accent.primary}` }} />}>Sea lane</Legend>
                  <Legend swatch={<Box sx={{ width: 18, borderTop: `2px dashed ${amber}` }} />}>Truck / rail leg</Legend>
                  <Legend swatch={<Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: t.accent.primary, boxShadow: `0 0 0 3px ${t.accent.primaryMuted}` }} />}>Vessel (estimated)</Legend>
                </Box>
              </Box>

              <Box ref={mapRef} data-testid="otw-map" sx={{ position: 'relative', width: '100%', aspectRatio: `${BASEMAP_SIZE.width} / ${BASEMAP_SIZE.height}`, borderRadius: 1, overflow: 'hidden' }}>
                <svg
                  viewBox={`0 0 ${BASEMAP_SIZE.width} ${BASEMAP_SIZE.height}`}
                  role="img"
                  aria-label="Map from Western Europe to East Asia showing the sea lanes into Durban"
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }}
                >
                  <path d={BASEMAP_DOTS} fill="none" stroke={theme.palette.mode === 'dark' ? 'rgba(160,185,205,0.28)' : 'rgba(40,70,95,0.30)'} strokeWidth="2.4" strokeLinecap="round" />
                  {data.map.lanes.map((l) =>
                    l.kind === 'sea' ? (
                      <g key={l.id}>
                        <path d={l.d} fill="none" stroke={t.accent.primary} strokeOpacity="0.22" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
                        <path d={l.d} fill="none" stroke={t.accent.primary} strokeOpacity="0.75" strokeWidth="1.6" strokeDasharray="2 7" strokeLinecap="round" strokeLinejoin="round" />
                      </g>
                    ) : (
                      <path key={l.id} d={l.d} fill="none" stroke={amber} strokeOpacity="0.9" strokeWidth="1.8" strokeDasharray="5 5" strokeLinecap="round" strokeLinejoin="round" />
                    ),
                  )}
                </svg>

                {data.map.ports.map((p) => {
                  const named = portNamed(p.id);
                  // Only a port that is a bare dot on a phone-width map can be tapped; it is a 44 px target under the vessels.
                  const tappable = compactPorts && !namedPorts?.has(p.id);
                  return (
                    <Box key={p.id} sx={{ position: 'absolute', left: `${p.x}%`, top: `${p.y}%`, transform: 'translate(-50%, -50%)', pointerEvents: tappable ? 'auto' : 'none' }}>
                      {tappable ? (
                        <Box
                          component="button"
                          type="button"
                          data-testid={`otw-port-dot-${p.id}`}
                          aria-label={`${p.label.charAt(0)}${p.label.slice(1).toLowerCase()}`}
                          aria-pressed={tappedPort === p.id}
                          onClick={() => setTappedPort((cur) => (cur === p.id ? null : p.id))}
                          sx={{ position: 'absolute', left: '50%', top: '50%', width: 44, height: 44, transform: 'translate(-50%, -50%)', border: 0, p: 0, bgcolor: 'transparent', cursor: 'pointer' }}
                        />
                      ) : null}
                      <Box component="span" sx={{ display: 'block', width: 7, height: 7, borderRadius: '50%', bgcolor: t.text.primary, boxShadow: `0 0 0 2px ${t.bg.default}` }} />
                      {named ? (
                        <Box component="span" data-testid={`otw-port-name-${p.id}`} sx={{ position: 'absolute', ...labelPlace(p.label_side ?? (p.x > 82 ? 'left' : 'right')), whiteSpace: 'nowrap', fontSize: 11, fontWeight: 600, letterSpacing: '.04em', color: t.text.primary, pointerEvents: 'none' }}>
                          {p.label}
                        </Box>
                      ) : null}
                    </Box>
                  );
                })}

                {durban && data.tiles.at_sea.overdue_vessels > 0 ? (
                  <Box
                    aria-hidden
                    data-testid="otw-pulse"
                    sx={{
                      position: 'absolute', left: `${durban.x}%`, top: `${durban.y}%`, width: 26, height: 26, borderRadius: '50%', border: `2px solid ${amber}`,
                      animation: 'otwPulse 2.4s ease-out infinite',
                      '@keyframes otwPulse': { '0%': { transform: 'translate(-50%, -50%) scale(.6)', opacity: 0.9 }, '100%': { transform: 'translate(-50%, -50%) scale(2.6)', opacity: 0 } },
                      '@media (prefers-reduced-motion: reduce)': { animation: 'none', opacity: 0.35, transform: 'translate(-50%, -50%)' },
                    }}
                  />
                ) : null}

                {clusters.map((c) => (
                  <ClusterMarker key={c.id} cluster={c} pickedId={picked?.id ?? null} onPick={onSelectVessel} onHover={setHoverId} t={t} amber={amber} />
                ))}

                {clusters.map((c) => {
                  const multi = c.vessels.length > 1;
                  const box = labelOf.get(multi ? `c:${c.id}` : c.vessels[0].id);
                  if (!box) return null;
                  const chip = multi ? clusterChip(c, data.map.ports) : null;
                  const v = c.vessels[0];
                  return (
                    <Box
                      key={`l-${c.id}`}
                      data-testid="otw-label"
                      sx={{
                        position: 'absolute', left: `${box.x}%`, top: `${box.y}%`, px: 1.1, py: 0.75, borderRadius: 1, whiteSpace: 'nowrap', pointerEvents: 'none',
                        bgcolor: alpha(t.bg.default, 0.86), border: `1px solid ${multi ? alpha(amber, 0.55) : v.id === panel?.id ? alpha(t.accent.primary, 0.7) : t.border.subtle}`,
                      }}
                    >
                      <Box sx={{ fontSize: 12, fontWeight: 700 }}>{chip ? chip.title : `${v.forwarder} · ${fmtUnits(v.units)} u`}</Box>
                      <Box sx={{ fontSize: 11, color: t.text.secondary, fontVariantNumeric: 'tabular-nums' }}>
                        {chip ? chip.sub : `${v.overdue ? daysText(v) : `ETA at port ${fmtDay(v.eta)}`}${v.slip_days ? ` · moved +${v.slip_days}d` : v.overdue ? '' : ' · on time'}`}
                      </Box>
                    </Box>
                  );
                })}

                {hoverVessel ? <HoverCard vessel={hoverVessel} cluster={hoverCluster} t={t} /> : null}

                {!narrow ? <MapNotes /> : null}
                {noVessels ? (
                  <Typography sx={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: t.text.secondary }}>No vessels at sea in this view.</Typography>
                ) : null}
              </Box>
              {narrow ? <Box sx={{ px: 0.5, display: 'flex', flexDirection: 'column', gap: 0.75, alignItems: 'flex-start' }}><MapNotes /></Box> : null}
            </Box>

            <Box sx={{ flex: '1 1 360px', minWidth: 'min(360px, 100%)', display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {panel ? <SelectedPanel vessel={panel} picked={Boolean(picked)} t={t} amber={amber} /> : null}
              <Box sx={{ ...card, p: 1 }}>
                <Typography sx={{ fontSize: 13, fontWeight: 600, p: 1 }}>Arriving next</Typography>
                {data.vessels.map((v) => (
                  <Box
                    key={v.id}
                    component="button"
                    type="button"
                    aria-pressed={picked?.id === v.id}
                    onClick={() => onSelectVessel(picked?.id === v.id ? null : v.key)}
                    sx={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1.5, width: '100%', minHeight: 52, px: 1.25, py: 1, border: 0, borderRadius: 1,
                      cursor: 'pointer', font: 'inherit', color: t.text.primary, textAlign: 'left',
                      bgcolor: picked?.id === v.id ? t.accent.primaryMuted : 'transparent', boxShadow: picked?.id === v.id ? `inset 2px 0 0 ${t.accent.primary}` : 'none',
                    }}
                  >
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, minWidth: 0 }}>
                      <Box component="span" sx={{ fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.forwarder}</Box>
                      <Box component="span" sx={{ fontSize: 11, color: t.text.secondary, fontVariantNumeric: 'tabular-nums' }}>{`${fmtUnits(v.units)} units · ${fmtMoney(v.amount)}`}</Box>
                    </Box>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, alignItems: 'flex-end' }}>
                      <Box component="span" sx={{ fontSize: 13, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{fmtDay(v.eta)}</Box>
                      <SlipChip vessel={v} t={t} amber={amber} />
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>
          </Box>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 1.5 }}>
            <PortConditions rows={data.port_rows} t={t} amber={amber} card={card} />
            {data.needs_look ? <NeedsLookCard n={data.needs_look} onOpen={onOpenNeedsLook} t={t} card={card} /> : null}
            <SourcesCard t={t} amber={amber} card={card} />
          </Box>
        </>
      )}
    </Box>
  );
}

type Tok = ReturnType<typeof tokensFor>;

function Legend({ swatch, children }: { swatch: ReactNode; children: ReactNode }) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
      {swatch}
      {children}
    </Box>
  );
}

/** Where a port's name sits against its dot: left, right, or centred above it. */
function labelPlace(side: 'left' | 'right' | 'above') {
  if (side === 'above') return { left: '50%', top: '-24px', transform: 'translateX(-50%)' };
  return side === 'left' ? { right: '12px', top: '-6px' } : { left: '12px', top: '-6px' };
}

function SlipChip({ vessel, t, amber }: { vessel: Vessel; t: Tok; amber: string }) {
  const late = vessel.slip_days > 0 || vessel.overdue;
  const color = late ? amber : t.semantic.success;
  return (
    <Box component="span" sx={{ fontSize: 11, fontWeight: 600, px: 0.9, py: '1px', borderRadius: 999, color, bgcolor: alpha(color, 0.14) }}>
      {vessel.overdue && vessel.slip_days <= 0 ? 'Overdue' : slipShort(vessel)}
    </Box>
  );
}

function ClusterMarker({
  cluster, pickedId, onPick, onHover, t, amber,
}: { cluster: Cluster; pickedId: string | null; onPick: (key: string | null) => void; onHover: (id: string | null) => void; t: Tok; amber: string }) {
  const multi = cluster.vessels.length > 1;
  const lead = cluster.vessels.find((v) => v.id === pickedId) ?? cluster.vessels[0];
  const on = cluster.vessels.some((v) => v.id === pickedId);
  const late = cluster.vessels.some((v) => v.slip_days > 0 || v.overdue);
  const color = on ? t.accent.primary : late ? amber : t.accent.primary;
  const size = (on ? 16 : 11) + (multi ? 5 : 0);
  const aria = multi
    ? `${cluster.vessels.length} vessels near ${fmtDay(lead.eta)} ETA at port, ${fmtUnits(cluster.vessels.reduce((s, v) => s + v.units, 0))} units`
    : `${lead.forwarder}, ETA at port ${fmtDay(lead.eta)}, ${fmtUnits(lead.units)} units${lead.overdue ? `, ${daysText(lead)}` : ''}`;
  return (
    <Box
      component="button"
      type="button"
      aria-label={aria}
      aria-pressed={on}
      data-testid="otw-vessel"
      data-vessel={lead.id}
      onClick={() => onPick(on ? null : lead.key)}
      onMouseEnter={() => onHover(lead.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(lead.id)}
      onBlur={() => onHover(null)}
      sx={{
        position: 'absolute', left: `${cluster.x}%`, top: `${cluster.y}%`, transform: 'translate(-50%, -50%)', width: 44, height: 44, p: 0, border: 0, bgcolor: 'transparent',
        cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: t.text.primary,
        '&:focus-visible': { outline: `2px solid ${t.accent.primary}`, outlineOffset: 2, borderRadius: '50%' },
      }}
    >
      <Box component="span" sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: size, height: size, borderRadius: '50%', bgcolor: color, fontSize: 10, fontWeight: 700, color: t.bg.default, boxShadow: `0 0 0 ${on ? 6 : 4}px ${alpha(color, on ? 0.28 : 0.18)}, 0 0 18px ${color}` }}>
        {multi ? cluster.vessels.length : null}
      </Box>
    </Box>
  );
}

function HoverCard({ vessel, cluster, t }: { vessel: Vessel; cluster: Cluster | null; t: Tok }) {
  const right = vessel.x > 55;
  const multi = (cluster?.vessels.length ?? 1) > 1;
  return (
    <Box
      role="tooltip"
      data-testid="otw-hover-card"
      sx={{
        position: 'absolute', zIndex: 5, width: 300, top: `calc(${vessel.y}% - 12px)`, ...(right ? { right: `calc(${100 - vessel.x}% + 26px)` } : { left: `calc(${vessel.x}% + 26px)` }),
        transform: 'translateY(-50%)', p: 1.5, borderRadius: 1.25, bgcolor: alpha(t.bg.default, 0.97), border: `1px solid ${alpha(t.accent.primary, 0.6)}`, boxShadow: '0 12px 32px rgba(0,0,0,0.35)', pointerEvents: 'none',
      }}
    >
      {multi ? (
        <Box sx={{ mb: 1, fontSize: 11, color: t.text.secondary }}>{cluster!.vessels.length} vessels here; this is the soonest. Pick the others from the list.</Box>
      ) : null}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.5, alignItems: 'baseline' }}>
        <Box component="span" sx={{ fontSize: 13, fontWeight: 700 }}>{vessel.forwarder}</Box>
        <Box component="span" sx={{ fontSize: 11, color: t.text.secondary, fontVariantNumeric: 'tabular-nums' }}>{`ETA at port ${fmtDay(vessel.eta)} · ${fmtUnits(vessel.units)} u · ${fmtMoney(vessel.amount)}`}</Box>
      </Box>
      <CardLabel t={t}>Distributors</CardLabel>
      <Box sx={{ fontSize: 12, lineHeight: 1.45, fontVariantNumeric: 'tabular-nums' }}>{nameUnits(vessel.distributors, 5)}</Box>
      <CardLabel t={t}>Top products · units</CardLabel>
      <Box sx={{ fontSize: 12, lineHeight: 1.45, fontVariantNumeric: 'tabular-nums' }}>{nameUnits(vessel.products)}</Box>
      <Box sx={{ fontSize: 11, color: t.text.secondary, mt: 0.75 }}>
        {vessel.more_models > 0 ? `+${vessel.more_models} more models · click to see every line` : 'Click to see every line'}
      </Box>
    </Box>
  );
}

function CardLabel({ t, children }: { t: Tok; children: ReactNode }) {
  return <Box sx={{ fontSize: 11, letterSpacing: '.06em', textTransform: 'uppercase', color: t.text.muted, mt: 1 }}>{children}</Box>;
}

function SelectedPanel({ vessel: v, picked, t, amber }: { vessel: Vessel; picked: boolean; t: Tok; amber: string }) {
  const late = v.slip_days > 0 || v.overdue;
  return (
    <Box data-testid="otw-selected" sx={{ bgcolor: t.bg.surface, border: `1px solid ${alpha(t.accent.primary, 0.45)}`, borderRadius: 1.5, p: 2, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1.5 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          <Box sx={{ fontSize: 12, color: t.text.secondary }}>
            {picked ? 'Selected vessel' : 'Next to arrive'}
            {v.inferred ? ' · inferred' : ''}
          </Box>
          <Box sx={{ fontSize: 18, fontWeight: 700 }}>{v.vessel_name ?? v.forwarder}</Box>
          <Box sx={{ fontSize: 12, color: t.text.secondary }}>
            {v.lane_label}
            {v.route_assumed ? ' · route assumed' : ''}
          </Box>
        </Box>
        <Box component="span" sx={{ fontSize: 12, fontWeight: 700, px: 1.25, py: 0.5, borderRadius: 999, whiteSpace: 'nowrap', color: late ? amber : t.semantic.success, bgcolor: alpha(late ? amber : t.semantic.success, 0.16) }}>
          {badgeText(v)}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: t.text.secondary }}>
          <span>On board {fmtDay(v.on_board)}</span>
          <span>ETA at port {fmtDay(v.eta)} · {daysText(v)}</span>
        </Box>
        <Box sx={{ height: 6, borderRadius: 0.75, bgcolor: t.bg.surfaceMuted, overflow: 'hidden' }}>
          <Box role="progressbar" aria-label="Share of the voyage elapsed" aria-valuenow={v.position_known === false ? undefined : Math.round(v.pct)} aria-valuetext={v.position_known === false ? 'No ETA: share of the voyage elapsed is not known' : undefined} aria-valuemin={0} aria-valuemax={100} sx={{ height: '100%', width: v.position_known === false ? '0%' : `${v.pct}%`, background: `linear-gradient(90deg, ${alpha(t.accent.primary, 0.55)}, ${t.accent.primary})` }} />
        </Box>
      </Box>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 1.25 }}>
        <Stat label="Units" value={fmtUnits(v.units)} t={t} />
        <Stat label="Value" value={fmtMoney(v.amount)} t={t} />
        <Stat label="Deliveries" value={fmtUnits(v.deliveries)} t={t} />
      </Box>
      <Box sx={{ fontSize: 12, lineHeight: 1.5, color: t.text.secondary }}>
        <span style={{ opacity: 0.8 }}>Distributors </span>
        <Box component="span" sx={{ color: t.text.primary }}>{nameUnits(v.distributors, 6)}</Box>
      </Box>
      <Box sx={{ fontSize: 12, lineHeight: 1.5, color: t.text.secondary }}>
        <span style={{ opacity: 0.8 }}>Top products </span>
        <Box component="span" sx={{ color: t.text.primary }}>
          {nameUnits(v.products)}
          {v.more_models > 0 ? ` · +${v.more_models} more models` : ''}
        </Box>
      </Box>
      <Box sx={{ fontSize: 12, color: t.text.secondary }}>
        <span style={{ opacity: 0.8 }}>ETA history </span>
        <Box component="span" sx={{ color: t.text.primary }}>{historyText(v)}</Box>
      </Box>
      <Box sx={{ fontSize: 11, color: t.text.muted, borderTop: `1px solid ${t.border.subtle}`, pt: 1.25 }}>
        {v.inferred
          ? 'Grouped by matching on-board date and ETA. Vessel name and container numbers are not on the report yet.'
          : 'Grouped by vessel name and voyage from the report.'}
      </Box>
    </Box>
  );
}

function Stat({ label, value, t }: { label: string; value: string; t: Tok }) {
  return (
    <Box>
      <Box sx={{ fontSize: 11, color: t.text.secondary }}>{label}</Box>
      <Box sx={{ fontSize: 16, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</Box>
    </Box>
  );
}

export function conditionText(row: PortRow | undefined): string {
  const c = row?.condition;
  if (!c) return 'No figure entered · Planned';
  const days = c.delay_days === 1 ? '1 day' : `${Number.isInteger(c.delay_days) ? c.delay_days : c.delay_days.toFixed(1)} days`;
  return `${days} · entered by ${c.entered_by}, ${fmtDay(c.entered_at)}`;
}

function PortConditions({ rows, t, amber, card }: { rows: PortRow[]; t: Tok; amber: string; card: object }) {
  return (
    <Box data-testid="otw-ports" sx={{ ...card, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600 }}>Port conditions</Typography>
      {rows.length === 0 ? <Typography variant="body2" sx={{ color: t.text.secondary }}>No ports with cargo in this view.</Typography> : null}
      {rows.map((r) => (
        <Box key={r.code} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.25, fontSize: 13 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            <span>{r.label} ({r.code})</span>
            {r.waiting_units > 0 ? <Box component="span" sx={{ fontSize: 11, color: t.text.secondary, fontVariantNumeric: 'tabular-nums' }}>{fmtUnits(r.waiting_units)} units waiting</Box> : null}
          </Box>
          <Box component="span" sx={{ color: r.condition ? t.text.primary : amber, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{conditionText(r)}</Box>
        </Box>
      ))}
      <Box sx={{ fontSize: 11, color: t.text.muted }}>
        Waiting = arrived at port, no proof of delivery yet. Port delay is entered by hand until a congestion feed is chosen.{' '}
        <MuiLink component={NextLink} href="/admin/port-conditions" underline="hover" data-testid="otw-enter-condition">
          Enter a figure
        </MuiLink>
      </Box>
    </Box>
  );
}

function NeedsLookCard({ n, onOpen, t, card }: { n: NonNullable<OnTheWaterData['needs_look']>; onOpen: () => void; t: Tok; card: object }) {
  return (
    <Box data-testid="otw-needs-look" sx={{ ...card, borderColor: alpha(t.semantic.danger, 0.5), display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600 }}>Needs a look</Typography>
      <Box sx={{ fontSize: 13, lineHeight: 1.5 }}>
        {`${fmtUnits(n.lines)} ${n.lines === 1 ? 'line' : 'lines'}, ${fmtUnits(n.units)} units, on the Shipped sheet with no ship confirm date${n.since ? ` since ${fmtDay(n.since)}` : ''}.`}
        {n.on_board_moved?.from && n.on_board_moved.to ? ` On-board date moved ${fmtDay(n.on_board_moved.from)} → ${fmtDay(n.on_board_moved.to)}.` : ''}
      </Box>
      <Box sx={{ fontSize: 12, color: t.text.secondary }}>{nameUnits(n.distributors, 6)}</Box>
      <Button size="small" variant="text" onClick={onOpen} sx={{ alignSelf: 'flex-start', px: 0, minHeight: 32, fontWeight: 600 }} data-testid="otw-open-needs-look">
        {`Open the ${n.lines} ${n.lines === 1 ? 'line' : 'lines'}`}
      </Button>
    </Box>
  );
}

function SourcesCard({ t, amber, card }: { t: Tok; amber: string; card: object }) {
  const rows: Array<[string, string, string]> = [
    ['On-board, ETA, arrival, POD, forwarder, port', 'Every report', t.semantic.success],
    ['ETA changes across reports', 'Report history', t.semantic.success],
    ['Live vessel position', 'Planned · needs vessel / B/L', amber],
    ['Port waiting times', 'Planned · congestion feed', amber],
  ];
  return (
    <Box sx={{ ...card, display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600 }}>Where the data comes from</Typography>
      {rows.map(([what, where, color]) => (
        <Box key={what} sx={{ display: 'flex', justifyContent: 'space-between', gap: 1.25, fontSize: 13 }}>
          <span>{what}</span>
          <Box component="span" sx={{ color, textAlign: 'right' }}>{where}</Box>
        </Box>
      ))}
    </Box>
  );
}

