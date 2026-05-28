import type { SxProps, Theme } from '@mui/material/styles';

/** Scrollbar colors aligned with CIP enterprise theme (WebKit + Firefox). */
export function themedScrollbarSx(): SxProps<Theme> {
  return (theme) => {
    const track = theme.palette.background.default;
    const thumb = theme.palette.mode === 'dark' ? 'rgba(120, 160, 190, 0.38)' : 'rgba(0, 0, 0, 0.28)';
    const thumbHover = theme.palette.primary.main;
    return {
      scrollbarWidth: 'thin',
      scrollbarColor: `${thumb} ${track}`,
      '&::-webkit-scrollbar': {
        width: 10,
        height: 10,
      },
      '&::-webkit-scrollbar-track': {
        backgroundColor: track,
        borderRadius: 10,
      },
      '&::-webkit-scrollbar-thumb': {
        backgroundColor: thumb,
        borderRadius: 10,
        border: `2px solid ${track}`,
      },
      '&::-webkit-scrollbar-thumb:hover': {
        backgroundColor: thumbHover,
      },
      '&::-webkit-scrollbar-corner': {
        backgroundColor: track,
      },
    };
  };
}
